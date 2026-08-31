package main

import (
	"net"
	"sync"
	"time"
)

// pipe copies from src to dst, enforcing an idle read timeout, and returns the
// number of bytes transferred.
func pipe(dst, src net.Conn, idle time.Duration) int64 {
	buf := make([]byte, 32*1024)
	var total int64
	for {
		if idle > 0 {
			_ = src.SetReadDeadline(time.Now().Add(idle))
		}
		n, err := src.Read(buf)
		if n > 0 {
			if _, werr := dst.Write(buf[:n]); werr != nil {
				return total
			}
			total += int64(n)
		}
		if err != nil {
			return total
		}
	}
}

// relay runs a full-duplex copy between client and upstream. It returns bytes
// sent from client->upstream (up) and upstream->client (down). When either side
// finishes, both connections are closed to unblock the other direction.
func relay(client, upstream net.Conn, idle time.Duration) (up, down int64) {
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		up = pipe(upstream, client, idle)
		_ = upstream.Close()
		_ = client.Close()
	}()
	go func() {
		defer wg.Done()
		down = pipe(client, upstream, idle)
		_ = client.Close()
		_ = upstream.Close()
	}()
	wg.Wait()
	return up, down
}
