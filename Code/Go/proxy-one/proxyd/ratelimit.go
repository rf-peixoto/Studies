package main

import (
	"sync"
	"time"
)

// bucket is a simple token-bucket rate limiter.
type bucket struct {
	mu       sync.Mutex
	tokens   float64
	max      float64
	refill   float64 // tokens per second
	last     time.Time
}

func newBucket(rate, burst float64) *bucket {
	if burst <= 0 {
		burst = rate
	}
	return &bucket{tokens: burst, max: burst, refill: rate, last: time.Now()}
}

func (b *bucket) allow() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	now := time.Now()
	elapsed := now.Sub(b.last).Seconds()
	b.last = now
	b.tokens += elapsed * b.refill
	if b.tokens > b.max {
		b.tokens = b.max
	}
	if b.tokens >= 1 {
		b.tokens--
		return true
	}
	return false
}

// Limiter holds per-user rate buckets and per-user concurrent-connection
// counters, plus a per-source-IP pre-auth accept limiter to blunt unauthenticated
// connection floods before a token is ever checked.
type Limiter struct {
	mu       sync.Mutex
	buckets  map[string]*bucket // keyed by user
	conns    map[string]int     // active conns per user
	ipBucket map[string]*bucket // keyed by source IP (pre-auth)

	preAuthRate  float64
	preAuthBurst float64
}

func NewLimiter(preAuthRate, preAuthBurst float64) *Limiter {
	return &Limiter{
		buckets:      make(map[string]*bucket),
		conns:        make(map[string]int),
		ipBucket:     make(map[string]*bucket),
		preAuthRate:  preAuthRate,
		preAuthBurst: preAuthBurst,
	}
}

// AllowSourceIP applies the pre-auth per-IP accept limit. Returns false when the
// source is connecting too fast, before any credential work is done.
func (l *Limiter) AllowSourceIP(ip string) bool {
	if l.preAuthRate <= 0 {
		return true
	}
	l.mu.Lock()
	b, ok := l.ipBucket[ip]
	if !ok {
		b = newBucket(l.preAuthRate, l.preAuthBurst)
		l.ipBucket[ip] = b
	}
	l.mu.Unlock()
	return b.allow()
}

// AllowUser applies the per-token connection rate limit.
func (l *Limiter) AllowUser(user string, rate, burst float64) bool {
	if rate <= 0 {
		return true
	}
	l.mu.Lock()
	b, ok := l.buckets[user]
	if !ok {
		b = newBucket(rate, burst)
		l.buckets[user] = b
	}
	l.mu.Unlock()
	return b.allow()
}

// Acquire reserves a concurrent-connection slot for a user. Returns false if the
// per-token max would be exceeded. Pair every true result with a Release.
func (l *Limiter) Acquire(user string, max int) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	if max > 0 && l.conns[user] >= max {
		return false
	}
	l.conns[user]++
	return true
}

func (l *Limiter) Release(user string) {
	l.mu.Lock()
	if l.conns[user] > 0 {
		l.conns[user]--
	}
	l.mu.Unlock()
}
