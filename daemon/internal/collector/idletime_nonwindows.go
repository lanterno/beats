//go:build !windows

package collector

// idleSecondsWindows is the non-Windows counterpart to the real
// implementation in idletime_windows.go. See appinfo_stub_windows.go
// for why the runtime.GOOS switch needs an arm that compiles
// everywhere.
func idleSecondsWindows() float64 {
	return 0.0
}
