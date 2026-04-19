package collector

import "errors"

// ErrEventTapNotAvailable indicates that input event counting is not available.
// This happens when CGEventTap permissions are missing or the feature is not
// yet implemented (v1 stub).
var ErrEventTapNotAvailable = errors.New("event tap not available")

// StartEventTap starts counting input events (keystrokes, mouse moves).
// Returns a getAndReset function that atomically reads and resets the counter,
// and a stop function to clean up.
//
// v1 stub: always returns ErrEventTapNotAvailable. The cadence score
// defaults to 0.5 when the event tap is unavailable.
func StartEventTap() (getAndReset func() int64, stop func(), err error) {
	return nil, nil, ErrEventTapNotAvailable
}
