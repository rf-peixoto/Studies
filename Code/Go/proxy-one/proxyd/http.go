package main

import (
	"bufio"
	"context"
	"encoding/base64"
	"fmt"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// hopByHopHeaders must not be forwarded to the upstream origin.
var hopByHopHeaders = []string{
	"Proxy-Authorization", "Proxy-Authenticate", "Proxy-Connection",
	"Connection", "Keep-Alive", "Te", "Trailer", "Transfer-Encoding", "Upgrade",
}

// parseProxyAuth extracts (user, token) from a "Basic base64(user:pass)" header.
func parseProxyAuth(h string) (user, token string, ok bool) {
	const p = "Basic "
	if !strings.HasPrefix(h, p) {
		return "", "", false
	}
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(h[len(p):]))
	if err != nil {
		return "", "", false
	}
	i := strings.IndexByte(string(raw), ':')
	if i < 0 {
		return "", "", false
	}
	return string(raw[:i]), string(raw[i+1:]), true
}

func (s *Server) handleHTTP(conn net.Conn) {
	defer conn.Close()
	srcIP, _, _ := net.SplitHostPort(conn.RemoteAddr().String())

	if !s.lim.AllowSourceIP(srcIP) {
		s.log.Log(Event{Event: "reject", Proto: "http", SrcIP: srcIP, Reason: "ip_rate_limited"})
		return
	}

	br := bufio.NewReader(conn)
	for {
		_ = conn.SetReadDeadline(time.Now().Add(s.handshakeTimeout))
		req, err := http.ReadRequest(br)
		if err != nil {
			return
		}
		_ = conn.SetReadDeadline(time.Time{})

		authHeader := req.Header.Get("Proxy-Authorization")
		user, token, haveAuth := parseProxyAuth(authHeader)

		if req.Method == http.MethodConnect {
			// HTTPS tunnel. Auth is validated here, once per connection.
			s.httpConnect(conn, br, req, srcIP, user, token, haveAuth)
			return // connection becomes an opaque tunnel or is closed
		}

		// Plain HTTP forward proxy. Auth is validated per request.
		keepAlive := s.httpForward(conn, req, srcIP, user, token, haveAuth)
		if !keepAlive {
			return
		}
	}
}

// authOrReject validates credentials and applies rate/conn limits. On failure
// it logs and returns ok=false; the caller must respond appropriately.
func (s *Server) authOrReject(proto, method, srcIP, user, token string, haveAuth bool, destHost string, destPort int) (Token, bool, string) {
	if !haveAuth {
		s.log.Log(Event{Event: "reject", Proto: proto, SrcIP: srcIP, Method: method,
			DestHost: destHost, DestPort: destPort, Auth: "missing", Reason: "no_credentials"})
		return Token{}, false, "no_credentials"
	}
	res := s.store.Validate(user, token)
	if !res.OK {
		s.log.Log(Event{Event: "reject", Proto: proto, SrcIP: srcIP, User: user, Method: method,
			DestHost: destHost, DestPort: destPort, TokenPrefix: HashPrefix(token),
			Auth: "rejected", Reason: res.Reason})
		return Token{}, false, res.Reason
	}
	if !s.lim.AllowUser(user, res.Token.RatePerS, res.Token.Burst) {
		s.log.Log(Event{Event: "reject", Proto: proto, SrcIP: srcIP, User: user, Method: method,
			DestHost: destHost, DestPort: destPort, TokenPrefix: HashPrefix(token),
			Auth: "accepted", Reason: "rate_limited"})
		return Token{}, false, "rate_limited"
	}
	return res.Token, true, ""
}

func (s *Server) httpConnect(conn net.Conn, br *bufio.Reader, req *http.Request, srcIP, user, token string, haveAuth bool) {
	host, portStr, err := net.SplitHostPort(req.Host)
	if err != nil {
		host, portStr = req.Host, "443"
	}
	port, _ := strconv.Atoi(portStr)

	tok, ok, reason := s.authOrReject("https", "CONNECT", srcIP, user, token, haveAuth, host, port)
	if !ok {
		if reason == "no_credentials" {
			writeProxyAuthRequired(conn)
		} else {
			io.WriteString(conn, "HTTP/1.1 403 Forbidden\r\n\r\n")
		}
		return
	}

	if !s.lim.Acquire(user, tok.MaxConns) {
		io.WriteString(conn, "HTTP/1.1 429 Too Many Requests\r\n\r\n")
		s.log.Log(Event{Event: "reject", Proto: "https", SrcIP: srcIP, User: user,
			DestHost: host, DestPort: port, Auth: "accepted", Reason: "max_conns"})
		return
	}
	defer s.lim.Release(user)

	ctx, cancel := context.WithTimeout(context.Background(), s.dialTimeout)
	upstream, ip, err := s.guard.Dial(ctx, host, port, s.dialTimeout)
	cancel()
	if err != nil {
		io.WriteString(conn, "HTTP/1.1 502 Bad Gateway\r\n\r\n")
		s.log.Log(Event{Event: "connect_fail", Proto: "https", SrcIP: srcIP, User: user,
			DestHost: host, DestPort: port, Auth: "accepted", Reason: err.Error()})
		return
	}
	defer upstream.Close()

	io.WriteString(conn, "HTTP/1.1 200 Connection established\r\n\r\n")

	start := time.Now()
	// Any bytes the client already buffered after the CONNECT line belong to
	// the tunnel; flush them to the upstream first.
	if n := br.Buffered(); n > 0 {
		b, _ := br.Peek(n)
		upstream.Write(b)
		br.Discard(n)
	}
	up, down := relay(conn, upstream, s.idleTimeout)
	s.log.Log(Event{Event: "tunnel", Proto: "https", SrcIP: srcIP, User: user,
		TokenPrefix: HashPrefix(token), Method: "CONNECT", DestHost: host, DestPort: port,
		DestIP: ip.String(), Auth: "accepted", BytesUp: up, BytesDown: down,
		DurationMS: time.Since(start).Milliseconds()})
}

func (s *Server) httpForward(conn net.Conn, req *http.Request, srcIP, user, token string, haveAuth bool) (keepAlive bool) {
	if !req.URL.IsAbs() || req.URL.Host == "" {
		io.WriteString(conn, "HTTP/1.1 400 Bad Request\r\n\r\n")
		return false
	}
	host := req.URL.Hostname()
	port := 80
	if p := req.URL.Port(); p != "" {
		port, _ = strconv.Atoi(p)
	}

	tok, ok, reason := s.authOrReject("http", req.Method, srcIP, user, token, haveAuth, host, port)
	if !ok {
		if reason == "no_credentials" {
			writeProxyAuthRequired(conn)
		} else {
			io.WriteString(conn, "HTTP/1.1 403 Forbidden\r\n\r\n")
		}
		return false
	}

	if !s.lim.Acquire(user, tok.MaxConns) {
		io.WriteString(conn, "HTTP/1.1 429 Too Many Requests\r\n\r\n")
		return false
	}
	defer s.lim.Release(user)

	ctx, cancel := context.WithTimeout(context.Background(), s.dialTimeout)
	upstream, ip, err := s.guard.Dial(ctx, host, port, s.dialTimeout)
	cancel()
	if err != nil {
		io.WriteString(conn, "HTTP/1.1 502 Bad Gateway\r\n\r\n")
		s.log.Log(Event{Event: "connect_fail", Proto: "http", SrcIP: srcIP, User: user,
			Method: req.Method, DestHost: host, DestPort: port, Auth: "accepted", Reason: err.Error()})
		return false
	}
	defer upstream.Close()

	// Rewrite to origin-form and strip hop-by-hop headers before forwarding.
	outReq := req.Clone(context.Background())
	outReq.RequestURI = ""
	for _, h := range hopByHopHeaders {
		outReq.Header.Del(h)
	}
	clientKeepAlive := !req.Close && !strings.EqualFold(req.Header.Get("Connection"), "close")

	start := time.Now()
	_ = upstream.SetDeadline(time.Now().Add(s.idleTimeout))
	if err := outReq.Write(upstream); err != nil {
		return false
	}
	upBr := bufio.NewReader(upstream)
	resp, err := http.ReadResponse(upBr, outReq)
	if err != nil {
		io.WriteString(conn, "HTTP/1.1 502 Bad Gateway\r\n\r\n")
		return false
	}
	defer resp.Body.Close()

	// Signal connection reuse state honestly to the client.
	if clientKeepAlive {
		resp.Header.Set("Connection", "keep-alive")
	} else {
		resp.Header.Set("Connection", "close")
	}
	_ = conn.SetWriteDeadline(time.Now().Add(s.idleTimeout))
	n, _ := writeResponseCounting(conn, resp)

	s.log.Log(Event{Event: "request", Proto: "http", SrcIP: srcIP, User: user,
		TokenPrefix: HashPrefix(token), Method: req.Method, DestHost: host, DestPort: port,
		DestIP: ip.String(), Auth: "accepted", BytesDown: n,
		DurationMS: time.Since(start).Milliseconds()})

	_ = conn.SetWriteDeadline(time.Time{})
	return clientKeepAlive
}

// writeResponseCounting writes an HTTP response to w and returns the body byte
// count (approximate; headers excluded).
func writeResponseCounting(w io.Writer, resp *http.Response) (int64, error) {
	cw := &countWriter{w: w}
	// Write status line + headers manually so we can count the body separately.
	err := resp.Write(cw)
	return cw.n, err
}

type countWriter struct {
	w io.Writer
	n int64
}

func (c *countWriter) Write(p []byte) (int, error) {
	n, err := c.w.Write(p)
	c.n += int64(n)
	return n, err
}

func writeProxyAuthRequired(w io.Writer) {
	fmt.Fprint(w, "HTTP/1.1 407 Proxy Authentication Required\r\n"+
		"Proxy-Authenticate: Basic realm=\"proxyd\"\r\n"+
		"Content-Length: 0\r\n\r\n")
}
