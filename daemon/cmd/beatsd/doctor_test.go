package main

import (
	"net"
	"runtime"
	"strings"
	"testing"

	"github.com/ahmedElghable/beats/daemon/internal/editor"
)

func TestCheckEditorPort_OK(t *testing.T) {
	// Best-effort happy path — assumes nothing else is bound to the
	// default port at test time. If a parallel test or another beatsd
	// is running we'll skip rather than fail (this isn't the contract
	// we're testing here).
	if isDefaultPortInUse() {
		t.Skip("default editor port already in use; skipping happy path")
	}
	detail, err := checkEditorPort()
	if err != nil {
		t.Errorf("expected nil error when port is free, got %v", err)
	}
	if !strings.Contains(detail, "available") {
		t.Errorf("expected detail to mention availability, got %q", detail)
	}
}

func TestCheckEditorPort_FailsWhenPortAlreadyBound(t *testing.T) {
	// Bind the listener ourselves, then call the doctor check. It
	// should detect the conflict and return an error pointing at the
	// "another beatsd already running" possibility.
	addr := net.JoinHostPort("127.0.0.1", portString(editor.DefaultPort))
	l, err := net.Listen("tcp", addr)
	if err != nil {
		t.Skipf("could not bind %s ourselves: %v", addr, err)
	}
	defer l.Close()

	_, gotErr := checkEditorPort()
	if gotErr == nil {
		t.Fatal("expected an error when port is in use, got nil")
	}
	if !strings.Contains(gotErr.Error(), "in use") {
		t.Errorf("expected 'in use' in error, got %q", gotErr.Error())
	}
}

func TestCheckEventTap_NonDarwinFallsBackInformatively(t *testing.T) {
	// Linux / Windows runners hit the stub, which should report
	// "stub fallback" with NO error — informational, not a failure
	// (cadence just defaults to 0.5).
	if runtime.GOOS == "darwin" {
		t.Skip("happy/sad paths on darwin depend on Accessibility permission")
	}
	detail, err := checkEventTap()
	if err != nil {
		t.Errorf("non-darwin should not surface an error, got %v", err)
	}
	if !strings.Contains(detail, "stub fallback") {
		t.Errorf("expected stub-fallback detail, got %q", detail)
	}
}

// --- helpers ---

func isDefaultPortInUse() bool {
	addr := net.JoinHostPort("127.0.0.1", portString(editor.DefaultPort))
	l, err := net.Listen("tcp", addr)
	if err != nil {
		return true
	}
	_ = l.Close()
	return false
}

func portString(p int) string {
	// Tiny inline strconv to avoid pulling fmt/strconv into the test
	// file just for one int → string. Not worth the dep weight.
	if p == 0 {
		return "0"
	}
	digits := []byte{}
	for n := p; n > 0; n /= 10 {
		digits = append([]byte{byte('0' + n%10)}, digits...)
	}
	return string(digits)
}
