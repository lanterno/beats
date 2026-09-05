//go:build !windows

package collector

// frontmostAppWindows is the non-Windows counterpart to the real
// implementation in appinfo_windows.go.
//
// FrontmostApp dispatches on runtime.GOOS rather than build tags, so
// every arm of that switch has to compile on every platform. This arm
// is unreachable off Windows — runtime.GOOS can't be "windows" in a
// binary built for anything else — but it still has to exist.
func frontmostAppWindows() (bundleID, appName string) {
	return "", ""
}
