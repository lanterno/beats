package main

import (
	"context"
	"fmt"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
)

// authedClient builds an authenticated API client + a context with a
// short timeout, ready for the runRecent / runStats / runTop family
// of commands. Returns the canonical "not paired" / "keychain read
// failed" errors so the dispatch arms surface a consistent message
// regardless of which command the user invoked.
//
// The caller is responsible for calling cancel() — typical pattern:
//
//	c, ctx, cancel, err := authedClient(cfg, 10*time.Second)
//	if err != nil { return err }
//	defer cancel()
//
// Returns a nil cancel function on the error path so callers can
// `defer cancel()` unconditionally without a nil-check.
func authedClient(cfg *config.Config, timeout time.Duration) (*client.Client, context.Context, context.CancelFunc, error) {
	token, err := pair.LoadToken()
	if err != nil {
		return nil, nil, func() {}, fmt.Errorf("keychain read failed: %w", err)
	}
	if token == "" {
		return nil, nil, func() {}, fmt.Errorf("not paired — run `beatsd pair <code>`")
	}
	c := client.New(cfg.API.BaseURL, token)
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	return c, ctx, cancel, nil
}
