package main

import (
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"time"
)

const (
	socksVersion  = 0x05
	authNoAccept  = 0xFF
	authUserPass  = 0x02
	cmdConnect    = 0x01
	cmdBind       = 0x02
	cmdUDPAssoc   = 0x03
	atypIPv4      = 0x01
	atypDomain    = 0x03
	atypIPv6      = 0x04
	repSuccess    = 0x00
	repGenFail    = 0x01
	repNotAllowed = 0x02
	repHostUnreach = 0x04
	repConnRefused = 0x05
	repCmdNotSup  = 0x07
)

func (s *Server) handleSOCKS(conn net.Conn) {
	defer conn.Close()
	srcIP, _, _ := net.SplitHostPort(conn.RemoteAddr().String())

	if !s.lim.AllowSourceIP(srcIP) {
		s.log.Log(Event{Event: "reject", Proto: "socks5", SrcIP: srcIP, Reason: "ip_rate_limited"})
		return
	}

	_ = conn.SetDeadline(time.Now().Add(s.handshakeTimeout))

	// ---- Method negotiation: we only accept username/password. ----
	header := make([]byte, 2)
	if _, err := io.ReadFull(conn, header); err != nil || header[0] != socksVersion {
		return
	}
	nMethods := int(header[1])
	methods := make([]byte, nMethods)
	if _, err := io.ReadFull(conn, methods); err != nil {
		return
	}
	if !contains(methods, authUserPass) {
		conn.Write([]byte{socksVersion, authNoAccept})
		s.log.Log(Event{Event: "reject", Proto: "socks5", SrcIP: srcIP, Auth: "missing", Reason: "no_userpass_method"})
		return
	}
	conn.Write([]byte{socksVersion, authUserPass})

	// ---- RFC 1929 username/password sub-negotiation. ----
	user, token, err := readUserPass(conn)
	if err != nil {
		return
	}

	res := s.store.Validate(user, token)
	if !res.OK {
		conn.Write([]byte{0x01, 0x01}) // auth failure
		s.log.Log(Event{Event: "reject", Proto: "socks5", SrcIP: srcIP, User: user,
			TokenPrefix: HashPrefix(token), Auth: "rejected", Reason: res.Reason})
		return
	}
	if !s.lim.AllowUser(user, res.Token.RatePerS, res.Token.Burst) {
		conn.Write([]byte{0x01, 0x01})
		s.log.Log(Event{Event: "reject", Proto: "socks5", SrcIP: srcIP, User: user,
			Auth: "accepted", Reason: "rate_limited"})
		return
	}
	conn.Write([]byte{0x01, 0x00}) // auth success

	// ---- Request. ----
	// VER CMD RSV ATYP ...
	reqHead := make([]byte, 4)
	if _, err := io.ReadFull(conn, reqHead); err != nil || reqHead[0] != socksVersion {
		return
	}
	cmd := reqHead[1]
	atyp := reqHead[3]

	host, err := readAddr(conn, atyp)
	if err != nil {
		return
	}
	portBuf := make([]byte, 2)
	if _, err := io.ReadFull(conn, portBuf); err != nil {
		return
	}
	port := int(binary.BigEndian.Uint16(portBuf))

	if cmd != cmdConnect {
		// BIND and UDP ASSOCIATE are not supported by design.
		socksReply(conn, repCmdNotSup)
		s.log.Log(Event{Event: "reject", Proto: "socks5", SrcIP: srcIP, User: user,
			DestHost: host, DestPort: port, Auth: "accepted", Reason: "cmd_not_supported"})
		return
	}

	if !s.lim.Acquire(user, res.Token.MaxConns) {
		socksReply(conn, repGenFail)
		s.log.Log(Event{Event: "reject", Proto: "socks5", SrcIP: srcIP, User: user,
			DestHost: host, DestPort: port, Auth: "accepted", Reason: "max_conns"})
		return
	}
	defer s.lim.Release(user)

	ctx, cancel := context.WithTimeout(context.Background(), s.dialTimeout)
	upstream, ip, err := s.guard.Dial(ctx, host, port, s.dialTimeout)
	cancel()
	if err != nil {
		socksReply(conn, repHostUnreach)
		s.log.Log(Event{Event: "connect_fail", Proto: "socks5", SrcIP: srcIP, User: user,
			DestHost: host, DestPort: port, Auth: "accepted", Reason: err.Error()})
		return
	}
	defer upstream.Close()

	socksReply(conn, repSuccess)
	_ = conn.SetDeadline(time.Time{}) // clear handshake deadline for the tunnel

	start := time.Now()
	up, down := relay(conn, upstream, s.idleTimeout)
	s.log.Log(Event{Event: "tunnel", Proto: "socks5", SrcIP: srcIP, User: user,
		TokenPrefix: HashPrefix(token), Method: "CONNECT", DestHost: host, DestPort: port,
		DestIP: ip.String(), Auth: "accepted", BytesUp: up, BytesDown: down,
		DurationMS: time.Since(start).Milliseconds()})
}

func readUserPass(conn net.Conn) (user, pass string, err error) {
	// VER ULEN UNAME PLEN PASSWD
	head := make([]byte, 2)
	if _, err = io.ReadFull(conn, head); err != nil {
		return
	}
	if head[0] != 0x01 {
		return "", "", fmt.Errorf("bad auth version")
	}
	uname := make([]byte, int(head[1]))
	if _, err = io.ReadFull(conn, uname); err != nil {
		return
	}
	plen := make([]byte, 1)
	if _, err = io.ReadFull(conn, plen); err != nil {
		return
	}
	passwd := make([]byte, int(plen[0]))
	if _, err = io.ReadFull(conn, passwd); err != nil {
		return
	}
	return string(uname), string(passwd), nil
}

func readAddr(conn net.Conn, atyp byte) (string, error) {
	switch atyp {
	case atypIPv4:
		b := make([]byte, 4)
		if _, err := io.ReadFull(conn, b); err != nil {
			return "", err
		}
		return net.IP(b).String(), nil
	case atypIPv6:
		b := make([]byte, 16)
		if _, err := io.ReadFull(conn, b); err != nil {
			return "", err
		}
		return net.IP(b).String(), nil
	case atypDomain:
		l := make([]byte, 1)
		if _, err := io.ReadFull(conn, l); err != nil {
			return "", err
		}
		d := make([]byte, int(l[0]))
		if _, err := io.ReadFull(conn, d); err != nil {
			return "", err
		}
		return string(d), nil
	default:
		return "", fmt.Errorf("unknown atyp")
	}
}

// socksReply writes a minimal reply with a zeroed bound address.
func socksReply(conn net.Conn, rep byte) {
	conn.Write([]byte{socksVersion, rep, 0x00, atypIPv4, 0, 0, 0, 0, 0, 0})
}

func contains(b []byte, v byte) bool {
	for _, x := range b {
		if x == v {
			return true
		}
	}
	return false
}
