//go:build windows

package collector

import (
	"errors"
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

// ErrEventTapNotAvailable indicates that input event counting is not
// available. On Windows this is genuinely rare — Raw Input needs no
// permission grant and no elevation — so unlike the macOS event tap it
// signals a real fault (a window that wouldn't create, a device
// registration the OS refused) rather than a missing entitlement.
var ErrEventTapNotAvailable = errors.New("event tap not available")

// Win32 message and window constants. Named here rather than pulled
// from x/sys/windows because that package doesn't export the windowing
// layer — only the kernel and security surface.
const (
	wmDestroy = 0x0002
	wmClose   = 0x0010
	wmInput   = 0x00FF

	// HWND_MESSAGE is (HWND)-3. A window parented to it is
	// "message-only": never visible, never enumerated, not in the
	// z-order, and it receives no broadcast messages. It exists purely
	// as a delivery address for WM_INPUT.
	hwndMessage = ^uintptr(0) - 2

	// RIDEV_INPUTSINK delivers input even when our window is not in the
	// foreground — the entire point for a background daemon. It's also
	// why hwndTarget must be set.
	ridevInputSink = 0x00000100

	// HID usage page 1 ("Generic Desktop") and the two usages we count.
	usagePageGeneric = 0x01
	usageMouse       = 0x02
	usageKeyboard    = 0x06

	rawInputClassName = "BeatsRawInputSink"
)

var (
	procRegisterClassExW        = modUser32.NewProc("RegisterClassExW")
	procCreateWindowExW         = modUser32.NewProc("CreateWindowExW")
	procDestroyWindow           = modUser32.NewProc("DestroyWindow")
	procDefWindowProcW          = modUser32.NewProc("DefWindowProcW")
	procGetMessageW             = modUser32.NewProc("GetMessageW")
	procDispatchMessageW        = modUser32.NewProc("DispatchMessageW")
	procPostMessageW            = modUser32.NewProc("PostMessageW")
	procPostQuitMessage         = modUser32.NewProc("PostQuitMessage")
	procRegisterRawInputDevices = modUser32.NewProc("RegisterRawInputDevices")

	procGetModuleHandleW = modKernel32.NewProc("GetModuleHandleW")
)

// eventCount is incremented once per input event, from the window
// procedure below.
//
// Package-level rather than per-tap because syscall.NewCallback
// produces a plain C function pointer with nowhere to hang a closure —
// the same constraint cadence_darwin.go works around with a static C
// counter. The tapMu guard below makes single-ownership explicit so
// two concurrent taps can't both add into it.
var eventCount atomic.Int64

var (
	tapMu     sync.Mutex
	tapActive bool
)

// wndProcCallback is created exactly once, at package init.
// syscall.NewCallback allocates from a small process-wide table that is
// never reclaimed, so creating one per StartEventTap call would leak a
// slot on every daemon restart of the tap.
var wndProcCallback = syscall.NewCallback(rawInputWndProc)

// classOnce guards window-class registration, which is process-wide and
// fails with ERROR_CLASS_ALREADY_EXISTS on a second attempt.
var (
	classOnce sync.Once
	classErr  error
	classAtom uintptr
)

type rawInputDevice struct {
	usUsagePage uint16
	usUsage     uint16
	dwFlags     uint32
	hwndTarget  uintptr
}

type wndClassExW struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     uintptr
	hIcon         uintptr
	hCursor       uintptr
	hbrBackground uintptr
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       uintptr
}

type msgW struct {
	hwnd    uintptr
	message uint32
	wParam  uintptr
	lParam  uintptr
	time    uint32
	pt      struct{ x, y int32 }
}

// rawInputWndProc is the window procedure for the message-only sink.
//
// PRIVACY: the WM_INPUT arm is one atomic increment and nothing else.
// We deliberately never call GetRawInputData, so the keycode, the
// mouse delta and the device handle are never read into this process
// at all — the event's existence is the entire payload. This is a
// stronger guarantee than the macOS tap can make, since a CGEventTap
// callback is handed the event whether it inspects it or not. A
// privacy audit of input handling on Windows is this one function.
func rawInputWndProc(hwnd, uMsg, wParam, lParam uintptr) uintptr {
	switch uint32(uMsg) {
	case wmInput:
		eventCount.Add(1)
		// Deliberately falls through to DefWindowProc: the WM_INPUT
		// docs require it so the system can release the input buffer.

	case wmClose:
		procDestroyWindow.Call(hwnd)
		return 0

	case wmDestroy:
		procPostQuitMessage.Call(0)
		return 0
	}

	ret, _, _ := procDefWindowProcW.Call(hwnd, uMsg, wParam, lParam)
	return ret
}

// StartEventTap starts counting input events via Raw Input.
//
// Returns a getAndReset function that atomically reads and resets the
// counter, and a stop function to tear the sink down.
//
// Raw Input rather than the WH_KEYBOARD_LL / WH_MOUSE_LL hooks the
// obvious search results suggest, for three reasons: low-level hooks
// put this process on the synchronous delivery path for every input
// event in the session (a slow callback stalls the whole desktop, and
// Windows silently evicts hooks that exceed LowLevelHooksTimeout),
// they require a message pump anyway so they're no simpler, and a
// process installing global input hooks is a well-known antivirus
// heuristic. Raw Input has none of those properties.
func StartEventTap() (getAndReset func() int64, stop func(), err error) {
	tapMu.Lock()
	if tapActive {
		tapMu.Unlock()
		return nil, nil, errors.New("event tap already running")
	}
	tapActive = true
	tapMu.Unlock()

	releaseTap := func() {
		tapMu.Lock()
		tapActive = false
		tapMu.Unlock()
	}

	type startResult struct {
		hwnd uintptr
		err  error
	}
	ready := make(chan startResult, 1)
	done := make(chan struct{})

	go func() {
		// The window, its message queue and the raw-input registration
		// are all bound to the OS thread that created them. Without
		// this lock the Go scheduler could migrate the goroutine and
		// the pump would read a queue that receives nothing.
		runtime.LockOSThread()
		defer runtime.UnlockOSThread()
		defer close(done)

		hwnd, err := createRawInputSink()
		ready <- startResult{hwnd: hwnd, err: err}
		if err != nil {
			return
		}
		pumpMessages()
	}()

	res := <-ready
	if res.err != nil {
		releaseTap()
		return nil, nil, res.err
	}

	// Discard anything counted between registration and here so the
	// first window measures a full interval rather than a partial one.
	eventCount.Store(0)

	var stopOnce sync.Once
	return func() int64 {
			return eventCount.Swap(0)
		}, func() {
			stopOnce.Do(func() {
				procPostMessageW.Call(res.hwnd, wmClose, 0, 0)
				<-done
				releaseTap()
			})
		}, nil
}

// createRawInputSink builds the message-only window and registers for
// keyboard and mouse input. Must run on the locked OS thread.
func createRawInputSink() (uintptr, error) {
	className, err := windows.UTF16PtrFromString(rawInputClassName)
	if err != nil {
		return 0, fmt.Errorf("%w: class name: %v", ErrEventTapNotAvailable, err)
	}

	hInst, _, _ := procGetModuleHandleW.Call(0)

	if err := registerRawInputClass(hInst, className); err != nil {
		return 0, err
	}

	hwnd, _, callErr := procCreateWindowExW.Call(
		0,                                  // dwExStyle
		uintptr(unsafe.Pointer(className)), // lpClassName
		uintptr(unsafe.Pointer(className)), // lpWindowName
		0,                                  // dwStyle
		0, 0, 0, 0,                         // x, y, width, height
		hwndMessage, // hWndParent — message-only
		0,           // hMenu
		hInst,       // hInstance
		0,           // lpParam
	)
	if hwnd == 0 {
		return 0, fmt.Errorf("%w: CreateWindowExW: %v", ErrEventTapNotAvailable, callErr)
	}

	devices := [2]rawInputDevice{
		{usUsagePage: usagePageGeneric, usUsage: usageKeyboard, dwFlags: ridevInputSink, hwndTarget: hwnd},
		{usUsagePage: usagePageGeneric, usUsage: usageMouse, dwFlags: ridevInputSink, hwndTarget: hwnd},
	}
	ret, _, callErr := procRegisterRawInputDevices.Call(
		uintptr(unsafe.Pointer(&devices[0])),
		uintptr(len(devices)),
		unsafe.Sizeof(devices[0]),
	)
	if ret == 0 {
		procDestroyWindow.Call(hwnd)
		return 0, fmt.Errorf("%w: RegisterRawInputDevices: %v", ErrEventTapNotAvailable, callErr)
	}

	// No explicit RIDEV_REMOVE on teardown: destroying hwndTarget
	// deregisters the devices, which is the documented behaviour and
	// the only path that also covers a crash.
	return hwnd, nil
}

func registerRawInputClass(hInst uintptr, className *uint16) error {
	classOnce.Do(func() {
		wc := wndClassExW{
			lpfnWndProc:   wndProcCallback,
			hInstance:     hInst,
			lpszClassName: className,
		}
		wc.cbSize = uint32(unsafe.Sizeof(wc))

		atom, _, callErr := procRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc)))
		if atom == 0 {
			// A class surviving from an earlier tap in this process is
			// success, not failure — the registration is process-wide
			// and outlives any individual window.
			if errno, ok := callErr.(syscall.Errno); ok && errno == windows.ERROR_CLASS_ALREADY_EXISTS {
				return
			}
			classErr = fmt.Errorf("%w: RegisterClassExW: %v", ErrEventTapNotAvailable, callErr)
			return
		}
		classAtom = atom
	})
	return classErr
}

// pumpMessages runs the message loop until WM_QUIT. Must run on the
// locked OS thread that created the window.
//
// TranslateMessage is deliberately absent: it exists to turn key
// events into WM_CHAR text, which is precisely the thing this daemon
// must never see.
func pumpMessages() {
	var m msgW
	for {
		ret, _, _ := procGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		// GetMessageW: >0 normal, 0 on WM_QUIT, -1 on error.
		if int32(ret) <= 0 {
			return
		}
		procDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
	}
}

// ProbeEventTap reports whether input counting is actually available,
// by building the real sink and tearing it straight back down.
//
// This does the genuine thing rather than returning a hardcoded nil:
// `beatsd doctor` is the tool a user reaches for when the flow score
// looks wrong, so a check that cannot fail is worse than no check.
// Setup and teardown are a handful of syscalls — fast enough to run
// synchronously inside doctor.
func ProbeEventTap() error {
	_, stop, err := StartEventTap()
	if err != nil {
		return err
	}
	stop()
	return nil
}
