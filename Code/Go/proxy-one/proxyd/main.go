package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"syscall"
	"time"
)

// Config is the persistent configuration read from config.json. CLI flags can
// override a subset of these at launch.
type Config struct {
	HTTPAddr          string   `json:"http_addr"`           // e.g. ":8080" ("" disables)
	SOCKSAddr         string   `json:"socks_addr"`          // e.g. ":1080" ("" disables)
	TokenDB           string   `json:"token_db"`            // path to tokens.json
	LogFile           string   `json:"log_file"`            // path; "" = stderr
	LogAll            bool     `json:"log_all"`             // log dropped/unauth requests too
	PidFile           string   `json:"pid_file"`            //
	SSRFProtect       bool     `json:"ssrf_protect"`        // block private/reserved destinations
	ExtraBlockedCIDRs []string `json:"extra_blocked_cidrs"` //
	DialTimeoutSec    int      `json:"dial_timeout_sec"`    //
	IdleTimeoutSec    int      `json:"idle_timeout_sec"`    //
	HandshakeSec      int      `json:"handshake_timeout_sec"`
	PreAuthRate       float64  `json:"preauth_ip_rate"`  // per-source-IP accept rate
	PreAuthBurst      float64  `json:"preauth_ip_burst"` //
}

func defaultConfig() Config {
	return Config{
		HTTPAddr:       ":8080",
		SOCKSAddr:      ":1080",
		TokenDB:        "/etc/proxyd/tokens.json",
		LogFile:        "/var/log/proxyd/proxyd.log",
		LogAll:         false,
		PidFile:        "/run/proxyd/proxyd.pid",
		SSRFProtect:    true,
		DialTimeoutSec: 15,
		IdleTimeoutSec: 300,
		HandshakeSec:   15,
		PreAuthRate:    50,
		PreAuthBurst:   100,
	}
}

// Server holds the shared runtime state used by both protocol handlers.
type Server struct {
	cfg              Config
	store            *Store
	guard            *Guard
	lim              *Limiter
	log              *Logger
	dialTimeout      time.Duration
	idleTimeout      time.Duration
	handshakeTimeout time.Duration
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "serve":
		cmdServe(os.Args[2:])
	case "token":
		cmdToken(os.Args[2:])
	case "-h", "--help", "help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `proxyd - authenticated HTTP/HTTPS/SOCKS5 forward proxy

Usage:
  proxyd serve   [--config FILE] [--http-addr ADDR] [--socks-addr ADDR] [--log FILE] [--log-all]
  proxyd token   add    --config FILE --user NAME --days N [--rate R] [--burst B] [--max-conns M]
  proxyd token   revoke --config FILE --user NAME
  proxyd token   list   --config FILE
`)
}

func loadConfig(path string) (Config, error) {
	cfg := defaultConfig()
	if path == "" {
		return cfg, nil
	}
	b, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return cfg, nil // fall back to defaults
		}
		return cfg, err
	}
	if err := json.Unmarshal(b, &cfg); err != nil {
		return cfg, fmt.Errorf("parsing %s: %w", path, err)
	}
	return cfg, nil
}

func cmdServe(args []string) {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	configPath := fs.String("config", "/etc/proxyd/config.json", "path to config.json")
	httpAddr := fs.String("http-addr", "", "override HTTP/HTTPS listen address")
	socksAddr := fs.String("socks-addr", "", "override SOCKS5 listen address")
	logFile := fs.String("log", "", "override log file path")
	logAll := fs.Bool("log-all", false, "log dropped/unauthenticated requests too")
	_ = fs.Parse(args)

	cfg, err := loadConfig(*configPath)
	if err != nil {
		fatal(err)
	}
	// CLI overrides.
	if *httpAddr != "" {
		cfg.HTTPAddr = *httpAddr
	}
	if *socksAddr != "" {
		cfg.SOCKSAddr = *socksAddr
	}
	if *logFile != "" {
		cfg.LogFile = *logFile
	}
	if *logAll {
		cfg.LogAll = true
	}

	store, err := NewStore(cfg.TokenDB)
	if err != nil {
		fatal(fmt.Errorf("token store: %w", err))
	}
	guard, err := NewGuard(cfg.ExtraBlockedCIDRs, cfg.SSRFProtect)
	if err != nil {
		fatal(err)
	}
	logger, err := NewLogger(cfg.LogFile, cfg.LogAll)
	if err != nil {
		fatal(fmt.Errorf("logger: %w", err))
	}

	s := &Server{
		cfg:              cfg,
		store:            store,
		guard:            guard,
		lim:              NewLimiter(cfg.PreAuthRate, cfg.PreAuthBurst),
		log:              logger,
		dialTimeout:      time.Duration(cfg.DialTimeoutSec) * time.Second,
		idleTimeout:      time.Duration(cfg.IdleTimeoutSec) * time.Second,
		handshakeTimeout: time.Duration(cfg.HandshakeSec) * time.Second,
	}

	writePidFile(cfg.PidFile)
	defer os.Remove(cfg.PidFile)

	var listeners []net.Listener
	var wg sync.WaitGroup

	if cfg.HTTPAddr != "" {
		ln, err := net.Listen("tcp", cfg.HTTPAddr)
		if err != nil {
			fatal(fmt.Errorf("listen http %s: %w", cfg.HTTPAddr, err))
		}
		listeners = append(listeners, ln)
		wg.Add(1)
		go func() { defer wg.Done(); acceptLoop(ln, s.handleHTTP) }()
		fmt.Fprintf(os.Stderr, "proxyd: HTTP/HTTPS proxy on %s\n", cfg.HTTPAddr)
	}
	if cfg.SOCKSAddr != "" {
		ln, err := net.Listen("tcp", cfg.SOCKSAddr)
		if err != nil {
			fatal(fmt.Errorf("listen socks %s: %w", cfg.SOCKSAddr, err))
		}
		listeners = append(listeners, ln)
		wg.Add(1)
		go func() { defer wg.Done(); acceptLoop(ln, s.handleSOCKS) }()
		fmt.Fprintf(os.Stderr, "proxyd: SOCKS5 proxy on %s\n", cfg.SOCKSAddr)
	}
	if len(listeners) == 0 {
		fatal(fmt.Errorf("no listeners configured (set http_addr and/or socks_addr)"))
	}

	// Signals:
	//   SIGHUP  -> reload token DB (used by token.sh after add/revoke)
	//   SIGUSR1 -> reopen log file (used by logrotate postrotate)
	//   SIGINT/SIGTERM -> graceful shutdown
	sigc := make(chan os.Signal, 1)
	signal.Notify(sigc, syscall.SIGHUP, syscall.SIGUSR1, syscall.SIGINT, syscall.SIGTERM)
	for sig := range sigc {
		switch sig {
		case syscall.SIGHUP:
			if err := s.store.Reload(); err != nil {
				fmt.Fprintf(os.Stderr, "proxyd: token reload failed: %v\n", err)
			} else {
				fmt.Fprintln(os.Stderr, "proxyd: token DB reloaded")
			}
		case syscall.SIGUSR1:
			if err := s.log.Reopen(); err != nil {
				fmt.Fprintf(os.Stderr, "proxyd: log reopen failed: %v\n", err)
			}
		case syscall.SIGINT, syscall.SIGTERM:
			fmt.Fprintln(os.Stderr, "proxyd: shutting down")
			for _, ln := range listeners {
				ln.Close()
			}
			return
		}
	}
	wg.Wait()
}

func acceptLoop(ln net.Listener, handle func(net.Conn)) {
	for {
		conn, err := ln.Accept()
		if err != nil {
			return // listener closed
		}
		go handle(conn)
	}
}

func writePidFile(path string) {
	if path == "" {
		return
	}
	_ = os.MkdirAll(dir(path), 0o755)
	_ = os.WriteFile(path, []byte(strconv.Itoa(os.Getpid())+"\n"), 0o644)
}

func dir(p string) string {
	for i := len(p) - 1; i >= 0; i-- {
		if p[i] == '/' {
			return p[:i]
		}
	}
	return "."
}

// ---- token subcommand ----

func cmdToken(args []string) {
	if len(args) < 1 {
		fatal(fmt.Errorf("usage: proxyd token <add|revoke|list> ..."))
	}
	sub := args[0]
	fs := flag.NewFlagSet("token", flag.ExitOnError)
	configPath := fs.String("config", "/etc/proxyd/config.json", "path to config.json")
	user := fs.String("user", "", "username")
	days := fs.Int("days", 0, "time-to-live in days (0 = never expires)")
	rate := fs.Float64("rate", 10, "max new connections per second for this token")
	burst := fs.Float64("burst", 20, "connection burst allowance for this token")
	maxConns := fs.Int("max-conns", 50, "max concurrent connections for this token")
	_ = fs.Parse(args[1:])

	cfg, err := loadConfig(*configPath)
	if err != nil {
		fatal(err)
	}
	dbPath := cfg.TokenDB

	switch sub {
	case "add":
		if *user == "" {
			fatal(fmt.Errorf("--user is required"))
		}
		token, err := AddToken(dbPath, *user, *days, *rate, *burst, *maxConns)
		if err != nil {
			fatal(err)
		}
		// The plaintext token is printed exactly once.
		fmt.Printf("%s\n", token)
	case "revoke":
		if *user == "" {
			fatal(fmt.Errorf("--user is required"))
		}
		n, err := RevokeToken(dbPath, *user)
		if err != nil {
			fatal(err)
		}
		fmt.Fprintf(os.Stderr, "revoked %d token(s) for %q\n", n, *user)
	case "list":
		db, err := ListTokens(dbPath)
		if err != nil {
			fatal(err)
		}
		fmt.Printf("%-16s %-14s %-22s %-8s %-8s %-6s %-9s\n",
			"USER", "HASH", "EXPIRES", "RATE/S", "BURST", "MAXC", "STATUS")
		for _, t := range db.Tokens {
			status := "active"
			if t.Revoked {
				status = "revoked"
			} else if t.Expires != "" {
				if exp, e := time.Parse(time.RFC3339, t.Expires); e == nil && time.Now().After(exp) {
					status = "expired"
				}
			}
			exp := t.Expires
			if exp == "" {
				exp = "never"
			}
			fmt.Printf("%-16s %-14s %-22s %-8.0f %-8.0f %-6d %-9s\n",
				t.User, t.Hash[:12], exp, t.RatePerS, t.Burst, t.MaxConns, status)
		}
	default:
		fatal(fmt.Errorf("unknown token subcommand %q", sub))
	}
}

func fatal(err error) {
	fmt.Fprintf(os.Stderr, "proxyd: %v\n", err)
	os.Exit(1)
}
