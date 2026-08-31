package main

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"syscall"
	"time"
)

// Token is a single credential record. The plaintext token is NEVER stored;
// only its SHA-256 hash is persisted, so a leak of the DB file does not leak
// usable credentials.
type Token struct {
	User      string `json:"user"`
	Hash      string `json:"hash"` // hex(sha256(token))
	Created   string `json:"created"`
	Expires   string `json:"expires"` // RFC3339; empty means never
	Revoked   bool   `json:"revoked"`
	RatePerS  float64 `json:"rate_per_sec"` // per-token connection rate
	Burst     float64 `json:"burst"`        // per-token burst
	MaxConns  int     `json:"max_conns"`    // per-token concurrent connections
}

type tokenDB struct {
	Tokens []Token `json:"tokens"`
}

// Store is the in-memory, concurrency-safe view of the token DB used by the
// running proxy. It is rebuilt from disk on SIGHUP.
type Store struct {
	mu     sync.RWMutex
	path   string
	byHash map[string]Token
}

func NewStore(path string) (*Store, error) {
	s := &Store{path: path}
	if err := s.Reload(); err != nil {
		return nil, err
	}
	return s, nil
}

// Reload reads the token DB from disk and swaps it in atomically.
func (s *Store) Reload() error {
	db, err := readTokenDB(s.path)
	if err != nil {
		return err
	}
	m := make(map[string]Token, len(db.Tokens))
	for _, t := range db.Tokens {
		m[t.Hash] = t
	}
	s.mu.Lock()
	s.byHash = m
	s.mu.Unlock()
	return nil
}

// AuthResult describes the outcome of a validation attempt.
type AuthResult struct {
	OK     bool
	Reason string
	Token  Token
}

// Validate checks a (user, plaintext-token) pair in constant time and enforces
// expiry and revocation. The username is used only to fetch the candidate
// record; the security-critical comparison is on the token hash.
func (s *Store) Validate(user, token string) AuthResult {
	sum := sha256.Sum256([]byte(token))
	h := hex.EncodeToString(sum[:])

	s.mu.RLock()
	rec, found := s.byHash[h]
	s.mu.RUnlock()

	// Always perform a constant-time compare against a reference value to keep
	// timing uniform whether or not the hash exists.
	ref := h
	if !found {
		ref = "0000000000000000000000000000000000000000000000000000000000000000"
	}
	if subtle.ConstantTimeCompare([]byte(h), []byte(ref)) != 1 || !found {
		return AuthResult{OK: false, Reason: "unknown_token"}
	}
	// Username must match the record bound to this token.
	if subtle.ConstantTimeCompare([]byte(user), []byte(rec.User)) != 1 {
		return AuthResult{OK: false, Reason: "user_mismatch"}
	}
	if rec.Revoked {
		return AuthResult{OK: false, Reason: "revoked", Token: rec}
	}
	if rec.Expires != "" {
		exp, err := time.Parse(time.RFC3339, rec.Expires)
		if err == nil && time.Now().After(exp) {
			return AuthResult{OK: false, Reason: "expired", Token: rec}
		}
	}
	return AuthResult{OK: true, Token: rec}
}

// HashPrefix returns a short, non-reversible identifier for a token suitable
// for correlating log lines without exposing the secret.
func HashPrefix(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])[:12]
}

// ---- On-disk operations used by the `proxyd token ...` subcommands. ----

func readTokenDB(path string) (tokenDB, error) {
	var db tokenDB
	b, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return db, nil // empty DB is valid
		}
		return db, err
	}
	if len(b) == 0 {
		return db, nil
	}
	if err := json.Unmarshal(b, &db); err != nil {
		return db, fmt.Errorf("parsing token db %s: %w", path, err)
	}
	return db, nil
}

// withLock runs fn while holding an exclusive flock on <path>.lock, so
// concurrent token operations cannot corrupt the DB.
func withLock(path string, fn func() error) error {
	lockPath := path + ".lock"
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return err
	}
	lf, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o640)
	if err != nil {
		return err
	}
	defer lf.Close()
	if err := syscall.Flock(int(lf.Fd()), syscall.LOCK_EX); err != nil {
		return err
	}
	defer syscall.Flock(int(lf.Fd()), syscall.LOCK_UN)
	return fn()
}

func writeTokenDB(path string, db tokenDB) error {
	b, err := json.MarshalIndent(db, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o640); err != nil {
		return err
	}
	return os.Rename(tmp, path) // atomic swap
}

// AddToken creates a new token, appends it to the DB, and returns the plaintext
// secret (shown to the operator exactly once).
func AddToken(path, user string, days int, rate, burst float64, maxConns int) (string, error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	token := base64.RawURLEncoding.EncodeToString(raw)
	sum := sha256.Sum256([]byte(token))

	now := time.Now().UTC()
	rec := Token{
		User:     user,
		Hash:     hex.EncodeToString(sum[:]),
		Created:  now.Format(time.RFC3339),
		Revoked:  false,
		RatePerS: rate,
		Burst:    burst,
		MaxConns: maxConns,
	}
	if days > 0 {
		rec.Expires = now.Add(time.Duration(days) * 24 * time.Hour).Format(time.RFC3339)
	}

	err := withLock(path, func() error {
		db, err := readTokenDB(path)
		if err != nil {
			return err
		}
		db.Tokens = append(db.Tokens, rec)
		return writeTokenDB(path, db)
	})
	if err != nil {
		return "", err
	}
	return token, nil
}

// RevokeToken marks all tokens for a user as revoked. Returns how many were
// affected.
func RevokeToken(path, user string) (int, error) {
	count := 0
	err := withLock(path, func() error {
		db, err := readTokenDB(path)
		if err != nil {
			return err
		}
		for i := range db.Tokens {
			if db.Tokens[i].User == user && !db.Tokens[i].Revoked {
				db.Tokens[i].Revoked = true
				count++
			}
		}
		return writeTokenDB(path, db)
	})
	return count, err
}

// ListTokens returns the DB for display (never includes plaintext secrets).
func ListTokens(path string) (tokenDB, error) {
	return readTokenDB(path)
}
