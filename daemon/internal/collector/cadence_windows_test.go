//go:build windows

package collector

import (
	"errors"
	"testing"
)

// TestStartEventTap_LifecycleOnWindows exercises the parts of the Raw
// Input sink that cannot be reached from any other machine: window
// class registration, message-only window creation, RegisterRawInputDevices,
// and teardown via the posted WM_CLOSE.
//
// It deliberately does NOT assert that events were counted — a CI
// runner generates no keyboard or mouse input, so a non-zero count is
// unavailable as a signal. What's proven here is that the sink builds
// and tears down cleanly, which is where the syscall-level mistakes
// live.
func TestStartEventTap_LifecycleOnWindows(t *testing.T) {
	getAndReset, stop, err := StartEventTap()
	if err != nil {
		t.Fatalf("StartEventTap on windows: %v", err)
	}
	if getAndReset == nil || stop == nil {
		t.Fatal("StartEventTap returned nil callbacks with a nil error")
	}

	// Counter starts clean and reads without blocking.
	if n := getAndReset(); n < 0 {
		t.Errorf("event count = %d, want >= 0", n)
	}

	stop()

	// stop must be idempotent: the collector loop defers it, and a
	// caller that also stops explicitly must not deadlock on the
	// pump-goroutine channel or panic on a double close.
	stop()
}

// TestStartEventTap_RejectsConcurrentTaps covers the single-ownership
// guard. Two live sinks would both increment the package-level counter,
// silently doubling the cadence score — the counter is package-level
// because syscall.NewCallback has nowhere to hang a closure.
func TestStartEventTap_RejectsConcurrentTaps(t *testing.T) {
	_, stop, err := StartEventTap()
	if err != nil {
		t.Fatalf("first StartEventTap: %v", err)
	}
	defer stop()

	_, _, err = StartEventTap()
	if err == nil {
		t.Fatal("second concurrent StartEventTap should have been refused")
	}
}

// TestProbeEventTap_SucceedsOnWindows pins the doctor contract: Raw
// Input needs no permission grant and no elevation, so on a healthy
// interactive session the probe passes. If this ever fails in CI it
// means the sink cannot be built in a non-interactive session, which
// is exactly what `beatsd doctor` needs to report to a user running
// the daemon as a service.
func TestProbeEventTap_SucceedsOnWindows(t *testing.T) {
	if err := ProbeEventTap(); err != nil {
		if errors.Is(err, ErrEventTapNotAvailable) {
			t.Fatalf("Raw Input sink unavailable in this session: %v", err)
		}
		t.Fatalf("ProbeEventTap: %v", err)
	}
}

// TestStartEventTap_ClassRegistrationIsReusable guards the
// ERROR_CLASS_ALREADY_EXISTS path. The window class is process-wide and
// outlives any individual window, so the second and third taps in a
// process take a different branch through registerRawInputClass than
// the first.
func TestStartEventTap_ClassRegistrationIsReusable(t *testing.T) {
	for i := range 3 {
		_, stop, err := StartEventTap()
		if err != nil {
			t.Fatalf("StartEventTap iteration %d: %v", i, err)
		}
		stop()
	}
}
