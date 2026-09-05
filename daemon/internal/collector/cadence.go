//go:build !darwin && !windows

package collector

import "errors"

// ErrEventTapNotAvailable indicates that input event counting is not available.
// This happens when CGEventTap permissions are missing or the platform doesn't
// support input-event counting at all.
//
// Real implementations live in cadence_darwin.go (CGEventTap) and
// cadence_windows.go (Raw Input); this file is the fallback for
// everything else, which today means Linux.
var ErrEventTapNotAvailable = errors.New("event tap not available")

// StartEventTap starts counting input events (keystrokes, mouse moves).
// Returns a getAndReset function that atomically reads and resets the counter,
// and a stop function to clean up.
//
// Fallback: always returns ErrEventTapNotAvailable. The collector
// loop catches this and the cadence score defaults to 0.5.
func StartEventTap() (getAndReset func() int64, stop func(), err error) {
	return nil, nil, ErrEventTapNotAvailable
}

// ProbeEventTap is the fallback counterpart: always reports
// "not available" on platforms with no input-counting implementation.
func ProbeEventTap() error {
	return ErrEventTapNotAvailable
}
