package main

import (
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
)

// authedClient depends on the keychain via pair.LoadToken. Testing
// it directly is awkward because manipulating the keychain in a
// test would either nuke the developer's real paired token or
// require root/CI-level isolation. This test takes the safe path:
// run only when no token happens to be stored, otherwise skip.
//
// The cancel-on-error and "not paired" error message are the
// load-bearing contracts (callers `defer cancel()` unconditionally,
// dispatch arms forward the error verbatim) — both are observable
// here without writing to the keychain.

func TestAuthedClient_ReturnsNotPairedErrorWhenNoToken(t *testing.T) {
	tok, _ := pair.LoadToken()
	if tok != "" {
		t.Skip("skipping: a token is already stored in the keychain; refusing to clobber developer state")
	}

	cfg := &config.Config{}
	cfg.API.BaseURL = "http://localhost:7999"

	c, ctx, cancel, err := authedClient(cfg, 5*time.Second)

	if err == nil {
		t.Fatalf("expected an error when no token is paired, got nil")
	}
	if !strings.Contains(err.Error(), "not paired") {
		t.Errorf("expected 'not paired' in error, got: %v", err)
	}
	if c != nil {
		t.Errorf("expected nil client on error, got: %v", c)
	}
	if ctx != nil {
		t.Errorf("expected nil ctx on error, got: %v", ctx)
	}
	// cancel must be a non-nil no-op so callers can `defer cancel()`
	// unconditionally without a nil-check on the error path.
	if cancel == nil {
		t.Errorf("expected non-nil no-op cancel on error path")
	} else {
		// Should not panic.
		cancel()
	}
}
