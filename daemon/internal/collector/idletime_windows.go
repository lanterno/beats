//go:build windows

package collector

import (
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	modKernel32 = windows.NewLazySystemDLL("kernel32.dll")

	procGetLastInputInfo = modUser32.NewProc("GetLastInputInfo")
	procGetTickCount64   = modKernel32.NewProc("GetTickCount64")
)

// lastInputInfo mirrors LASTINPUTINFO. cbSize must be set to the
// struct's own size before the call or GetLastInputInfo fails.
type lastInputInfo struct {
	cbSize uint32
	dwTime uint32
}

// idleSecondsWindows returns seconds since the last keyboard or mouse
// input, session-wide.
//
// Unlike the macOS and Linux paths this shells out to nothing — it's
// two syscalls with no subprocess, so it's cheap enough to run on
// every 5-second poll without thought.
//
// One documented limitation worth knowing: GetLastInputInfo reports
// input for the session the calling process belongs to, and returns
// stale values while the workstation is locked. That's the behaviour
// we want — a locked machine should read as idle, and it does, because
// dwTime stops advancing.
func idleSecondsWindows() float64 {
	info := lastInputInfo{}
	info.cbSize = uint32(unsafe.Sizeof(info))

	ret, _, _ := procGetLastInputInfo.Call(uintptr(unsafe.Pointer(&info)))
	if ret == 0 {
		return 0.0
	}

	ticks, _, _ := procGetTickCount64.Call()
	return idleSecondsFromTicks(uint64(ticks), info.dwTime)
}
