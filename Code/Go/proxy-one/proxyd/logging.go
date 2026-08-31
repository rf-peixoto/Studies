package main

import (
	"encoding/json"
	"os"
	"sync"
	"time"
)

// Logger writes structured JSON-lines events to a file (or stderr when path is
// empty). It can reopen its file on demand so an external logrotate can rotate
// the log without the process losing its file descriptor.
type Logger struct {
	mu   sync.Mutex
	path string
	f    *os.File
	// logAll controls whether rejected/dropped (non-authenticated) events are
	// written. When false, only authenticated events are recorded.
	logAll bool
}

// Event is a single structured log record. Fields left at their zero value are
// omitted so each line stays compact and greppable.
type Event struct {
	TS          string `json:"ts"`
	Event       string `json:"event"`
	Proto       string `json:"proto,omitempty"`
	SrcIP       string `json:"src_ip,omitempty"`
	User        string `json:"user,omitempty"`
	TokenPrefix string `json:"token_prefix,omitempty"`
	Method      string `json:"method,omitempty"`
	DestHost    string `json:"dest_host,omitempty"`
	DestPort    int    `json:"dest_port,omitempty"`
	DestIP      string `json:"dest_ip,omitempty"`
	Auth        string `json:"auth,omitempty"`
	Reason      string `json:"reason,omitempty"`
	BytesUp     int64  `json:"bytes_up,omitempty"`
	BytesDown   int64  `json:"bytes_down,omitempty"`
	DurationMS  int64  `json:"duration_ms,omitempty"`
}

func NewLogger(path string, logAll bool) (*Logger, error) {
	l := &Logger{path: path, logAll: logAll}
	if err := l.reopen(); err != nil {
		return nil, err
	}
	return l, nil
}

// reopen (re)opens the underlying file. Called at startup and on SIGUSR1.
func (l *Logger) reopen() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.path == "" {
		l.f = os.Stderr
		return nil
	}
	f, err := os.OpenFile(l.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640)
	if err != nil {
		return err
	}
	if l.f != nil && l.f != os.Stderr {
		_ = l.f.Close()
	}
	l.f = f
	return nil
}

// Reopen is the exported hook used by the SIGUSR1 handler.
func (l *Logger) Reopen() error { return l.reopen() }

// authenticated reports whether an event represents a request that passed
// token authentication. Only these are logged unless logAll is set.
func authenticated(e *Event) bool { return e.Auth == "accepted" }

func (l *Logger) Log(e Event) {
	if !l.logAll && !authenticated(&e) {
		return
	}
	e.TS = time.Now().UTC().Format(time.RFC3339Nano)
	b, err := json.Marshal(&e)
	if err != nil {
		return
	}
	b = append(b, '\n')
	l.mu.Lock()
	if l.f != nil {
		_, _ = l.f.Write(b)
	}
	l.mu.Unlock()
}
