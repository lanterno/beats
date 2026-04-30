//go:build !darwin

package collector

import "errors"

// ErrEventTapNotAvailable indicates that input event counting is not available.
// This happens when CGEventTap permissions are missing or the platform doesn't
// support input-event counting at all (currently: anything but macOS).
var ErrEventTapNotAvailable = errors.New("event tap not available")

// StartEventTap starts counting input events (keystrokes, mouse moves).
// Returns a getAndReset function that atomically reads and resets the counter,
// and a stop function to clean up.
//
// Non-darwin fallback: always returns ErrEventTapNotAvailable. The collector
// loop catches this and the cadence score defaults to 0.5.
func StartEventTap() (getAndReset func() int64, stop func(), err error) {
	return nil, nil, ErrEventTapNotAvailable
}

// ProbeEventTap is the non-darwin counterpart: always reports
// "not available" since input-event counting is darwin-only.
func ProbeEventTap() error {
	return ErrEventTapNotAvailable
}
