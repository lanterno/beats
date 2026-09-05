//go:build windows

package collector

import (
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	modUser32 = windows.NewLazySystemDLL("user32.dll")

	procGetForegroundWindow      = modUser32.NewProc("GetForegroundWindow")
	procGetWindowThreadProcessId = modUser32.NewProc("GetWindowThreadProcessId")
)

// frontmostAppWindows returns the executable identity of the process
// owning the foreground window.
//
// The chain is GetForegroundWindow → GetWindowThreadProcessId →
// OpenProcess → QueryFullProcessImageName. Every step returns
// ("", "") on failure rather than an error: a sample with no app is a
// legitimate observation (the desktop is locked, the foreground window
// belongs to a process at a higher integrity level, nothing is
// focused), and the collector loop treats it as such.
//
// PROCESS_QUERY_LIMITED_INFORMATION is deliberately the narrowest
// access right that permits QueryFullProcessImageName. It succeeds
// against processes that PROCESS_QUERY_INFORMATION would be refused
// for, so the weaker right is also the more capable one here.
//
// We never read the window title — see windowsExeIdentity for why.
func frontmostAppWindows() (bundleID, appName string) {
	hwnd, _, _ := procGetForegroundWindow.Call()
	if hwnd == 0 {
		// No foreground window: locked workstation, or the focused
		// window belongs to another desktop.
		return "", ""
	}

	var pid uint32
	// Returns the thread id and writes the process id through the
	// out-param; a 0 return means the window handle was invalid.
	tid, _, _ := procGetWindowThreadProcessId.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
	if tid == 0 || pid == 0 {
		return "", ""
	}

	h, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
	if err != nil {
		// Most often an elevated process while we run unelevated. Not
		// an error worth logging every 5 seconds.
		return "", ""
	}
	defer windows.CloseHandle(h)

	// MAX_PATH is not a hard ceiling on modern Windows (long paths can
	// exceed it), so grow once rather than truncating a legitimate
	// path into a wrong app name.
	buf := make([]uint16, windows.MAX_PATH)
	for {
		size := uint32(len(buf))
		err := windows.QueryFullProcessImageName(h, 0, &buf[0], &size)
		if err == nil {
			return windowsExeIdentity(windows.UTF16ToString(buf[:size]))
		}
		if err != windows.ERROR_INSUFFICIENT_BUFFER || len(buf) >= 32768 {
			return "", ""
		}
		buf = make([]uint16, len(buf)*2)
	}
}
