package main

import (
	"context"
	"fmt"
	"net"
	"time"
)

// Guard validates destinations and dials only IPs that passed the blocklist
// check, closing the DNS-rebinding hole (validate a name, then connect to a
// different IP on the actual dial).
type Guard struct {
	blocked []*net.IPNet
	enabled bool
}

// defaultBlockedCIDRs covers loopback, private, link-local (incl. cloud
// metadata 169.254.169.254), CGNAT, benchmarking, and IPv6 equivalents.
var defaultBlockedCIDRs = []string{
	"0.0.0.0/8",
	"10.0.0.0/8",
	"100.64.0.0/10",
	"127.0.0.0/8",
	"169.254.0.0/16",
	"172.16.0.0/12",
	"192.0.0.0/24",
	"192.0.2.0/24",
	"192.168.0.0/16",
	"198.18.0.0/15",
	"198.51.100.0/24",
	"203.0.113.0/24",
	"224.0.0.0/4",
	"240.0.0.0/4",
	"::1/128",
	"::/128",
	"fc00::/7",
	"fe80::/10",
	"ff00::/8",
}

func NewGuard(extraCIDRs []string, enabled bool) (*Guard, error) {
	g := &Guard{enabled: enabled}
	all := append([]string{}, defaultBlockedCIDRs...)
	all = append(all, extraCIDRs...)
	for _, c := range all {
		_, n, err := net.ParseCIDR(c)
		if err != nil {
			return nil, fmt.Errorf("bad CIDR %q: %w", c, err)
		}
		g.blocked = append(g.blocked, n)
	}
	return g, nil
}

func (g *Guard) isBlocked(ip net.IP) bool {
	if ip == nil {
		return true
	}
	// Normalize IPv4-mapped IPv6 so a mapped private v4 can't slip through.
	if v4 := ip.To4(); v4 != nil {
		ip = v4
	}
	for _, n := range g.blocked {
		if n.Contains(ip) {
			return true
		}
	}
	return false
}

// Dial resolves host, rejects it if any resolved address is blocked, then
// connects directly to a validated IP. Returns the connection and the IP used.
func (g *Guard) Dial(ctx context.Context, host string, port int, timeout time.Duration) (net.Conn, net.IP, error) {
	// Literal IP path: validate directly.
	if ip := net.ParseIP(host); ip != nil {
		if g.enabled && g.isBlocked(ip) {
			return nil, ip, fmt.Errorf("destination blocked")
		}
		return dialIP(ctx, ip, port, timeout)
	}

	ips, err := net.DefaultResolver.LookupIP(ctx, "ip", host)
	if err != nil {
		return nil, nil, fmt.Errorf("resolve %s: %w", host, err)
	}
	if len(ips) == 0 {
		return nil, nil, fmt.Errorf("no addresses for %s", host)
	}
	if g.enabled {
		// Reject if ANY resolved record is internal — refuse to guess which one
		// the client would have used.
		for _, ip := range ips {
			if g.isBlocked(ip) {
				return nil, ip, fmt.Errorf("destination blocked")
			}
		}
	}
	// Dial the first validated address. Since we hand net.Dial the concrete IP
	// (not the name), no second, unvalidated resolution occurs.
	var lastErr error
	for _, ip := range ips {
		conn, used, err := dialIP(ctx, ip, port, timeout)
		if err == nil {
			return conn, used, nil
		}
		lastErr = err
	}
	return nil, nil, lastErr
}

func dialIP(ctx context.Context, ip net.IP, port int, timeout time.Duration) (net.Conn, net.IP, error) {
	d := net.Dialer{Timeout: timeout}
	addr := net.JoinHostPort(ip.String(), fmt.Sprintf("%d", port))
	conn, err := d.DialContext(ctx, "tcp", addr)
	return conn, ip, err
}
