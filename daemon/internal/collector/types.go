// Package collector provides macOS signal collection and Flow Score computation.
package collector

import "time"

// Sample is a single observation of the user's desktop state.
type Sample struct {
	CollectedAt time.Time
	BundleID    string  // e.g. "com.apple.dt.Xcode"
	AppName     string  // e.g. "Xcode"
	IdleSeconds float64 // seconds since last input event
	EventCount  int64   // input events since last sample; -1 = unavailable
}

// FlowWindow is a computed flow-state summary over a time window.
type FlowWindow struct {
	WindowStart      time.Time
	WindowEnd        time.Time
	FlowScore        float64 // composite [0, 1]
	CadenceScore     float64
	CoherenceScore   float64
	CategoryFitScore float64
	IdleFraction     float64
	DominantBundleID string
	DominantCategory string
	ContextSwitches  int
	ActiveProjectID  string // empty if no timer running
	// Editor context — set by the editor.Listener after the window is
	// computed. Empty when no fresh editor heartbeat is available.
	EditorRepo     string
	EditorBranch   string
	EditorLanguage string
}
