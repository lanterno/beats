package client

import (
	"sync"
	"time"
)

// The two refusals that mean the API will keep refusing this daemon until a
// person acts: the account is suspended, or this device's registration was
// revoked (roadmaps/backoffice.md step 1). Backing off to a slow probe is
// the right answer to both — retrying five endpoints every few seconds
// changes nothing and fills the log — and the probe is what lets the daemon
// notice on its own when the suspension lifts.
const (
	CodeAccountSuspended = "ACCOUNT_SUSPENDED"
	CodeDeviceRevoked    = "DEVICE_REVOKED"
)

// refused reports whether code is one of the two standing refusals.
func refused(code string) bool {
	return code == CodeAccountSuspended || code == CodeDeviceRevoked
}

// RefusalGate pauses the daemon's API traffic once the API has refused the
// account or the device, letting one call through per interval as a probe.
// Goroutine-safe: the flush loop, the timer-context poller and the drift
// posts all consult the same gate, and whichever of them lands first after
// the interval is the probe.
type RefusalGate struct {
	mu        sync.Mutex
	interval  time.Duration
	now       func() time.Time // injected by tests
	code      string           // "" when open
	nextProbe time.Time
}

// NewRefusalGate returns an open gate that, once closed by a refusal, lets
// one call through per interval.
func NewRefusalGate(interval time.Duration) *RefusalGate {
	return &RefusalGate{interval: interval, now: time.Now}
}

// Blocked reports whether an API call should be skipped right now. While
// refused it answers false once per interval — that call is the probe, and
// claiming it pushes the next one an interval out.
func (g *RefusalGate) Blocked() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.code == "" {
		return false
	}
	if g.now().Before(g.nextProbe) {
		return true
	}
	g.nextProbe = g.now().Add(g.interval)
	return false
}

// Note records an API call's failure. It closes the gate on a standing
// refusal and reports whether this call is the one that closed it, so the
// caller logs the refusal once rather than once per skipped call. Any other
// error leaves the gate as it is.
func (g *RefusalGate) Note(err error) (newlyRefused bool) {
	code := ErrorCode(err)
	if !refused(code) {
		return false
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	first := g.code != code
	g.code = code
	g.nextProbe = g.now().Add(g.interval)
	return first
}

// Clear opens the gate after a call succeeded, and reports whether it had
// been closed — the probe that got through — so the caller can log the
// recovery once.
func (g *RefusalGate) Clear() (wasRefused bool) {
	g.mu.Lock()
	defer g.mu.Unlock()
	was := g.code != ""
	g.code = ""
	return was
}

// Refusal returns the code the gate is closed on, or "" while open.
func (g *RefusalGate) Refusal() string {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.code
}

// RefusalWord renders a refusal code for a human: `beatsd status` and the
// daemon's own log say which refusal it was in these words.
func RefusalWord(code string) string {
	switch code {
	case CodeAccountSuspended:
		return "account suspended"
	case CodeDeviceRevoked:
		return "device revoked"
	default:
		return code
	}
}
