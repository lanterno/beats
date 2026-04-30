//go:build darwin

package collector

/*
#cgo CFLAGS: -x objective-c
#cgo LDFLAGS: -framework ApplicationServices -framework CoreFoundation

#include <ApplicationServices/ApplicationServices.h>
#include <stdint.h>

// Atomic counter incremented by every observed input event. Read and reset
// from Go via getAndResetCount(); the only thing crossing the cgo boundary
// from the callback is one __sync_add_and_fetch on this 64-bit integer.
static volatile int64_t eventCount = 0;

static CFMachPortRef tapRef = NULL;
static CFRunLoopSourceRef sourceRef = NULL;
static CFRunLoopRef tapRunLoop = NULL;

// Passive callback. We deliberately do NOT inspect the event itself — no
// keycodes, no mouse coordinates, no modifier state. The single statement
// is the entire body so a privacy audit is one grep away.
CGEventRef tapCallback(CGEventTapProxy proxy, CGEventType type,
                       CGEventRef event, void *refcon) {
    __sync_add_and_fetch(&eventCount, 1);
    return event;
}

// Returns 0 on success, -1 if the OS denied the tap (most often: missing
// Accessibility permission). Caller must not call runTapLoop() if this
// returns non-zero.
static int startTap() {
    CGEventMask mask = (1 << kCGEventKeyDown) |
                       (1 << kCGEventMouseMoved) |
                       (1 << kCGEventScrollWheel) |
                       (1 << kCGEventLeftMouseDown) |
                       (1 << kCGEventRightMouseDown);

    tapRef = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,  // passive — does not block or modify events
        mask,
        tapCallback,
        NULL
    );
    if (tapRef == NULL) {
        return -1;
    }

    sourceRef = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tapRef, 0);
    if (sourceRef == NULL) {
        CFRelease(tapRef);
        tapRef = NULL;
        return -1;
    }
    return 0;
}

// Blocks: spins a CFRunLoop on the calling thread that pumps events into
// tapCallback. Started on a background goroutine via cgo. After
// CFRunLoopRun returns (because stopTap signaled it to stop), this
// function owns the teardown — releasing the tap and source on the same
// thread that ran them avoids the cross-thread CFRelease race that bit
// `beatsd doctor` (CFRunLoopStop on thread A while CFRelease on thread B
// races against the run loop's exit-path touching the tap).
static void runTapLoop() {
    tapRunLoop = CFRunLoopGetCurrent();
    CFRunLoopAddSource(tapRunLoop, sourceRef, kCFRunLoopCommonModes);
    CGEventTapEnable(tapRef, true);
    CFRunLoopRun();

    // Run loop exited. Tear everything down on this thread.
    if (tapRef != NULL) {
        CGEventTapEnable(tapRef, false);
        CFRunLoopRemoveSource(tapRunLoop, sourceRef, kCFRunLoopCommonModes);
        CFRelease(tapRef);
        tapRef = NULL;
    }
    if (sourceRef != NULL) {
        CFRelease(sourceRef);
        sourceRef = NULL;
    }
    tapRunLoop = NULL;
}

// stopTap signals the run loop to exit. Cleanup of the tap + source
// happens inside runTapLoop after CFRunLoopRun returns — see the comment
// above. Calling stopTap twice or before startTap is a no-op.
static void stopTap() {
    if (tapRunLoop != NULL) {
        CFRunLoopStop(tapRunLoop);
    }
}

// Cheap "would CGEventTapCreate succeed?" probe for `beatsd doctor`. Used
// instead of starting + stopping the full run loop, which would hit the
// teardown path needlessly. Returns 0 on success (tap was created and
// immediately released), -1 if the OS refused (typically: no Accessibility
// permission).
static int probeEventTap() {
    CGEventMask mask = (1 << kCGEventKeyDown);
    CFMachPortRef probe = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        tapCallback,
        NULL
    );
    if (probe == NULL) {
        return -1;
    }
    CFRelease(probe);
    return 0;
}

static int64_t getAndResetCount() {
    return __sync_lock_test_and_set(&eventCount, 0);
}
*/
import "C"

import (
	"errors"
)

// ErrEventTapNotAvailable indicates that input event counting is not available.
// On darwin this most often means the user hasn't granted Accessibility
// permission to the daemon binary; the loop logs the upgrade hint once and
// the cadence score defaults to 0.5.
var ErrEventTapNotAvailable = errors.New("event tap not available — grant Accessibility permission to enable cadence tracking")

// ProbeEventTap returns nil if CGEventTapCreate would succeed right now —
// i.e. Accessibility permission is granted — and ErrEventTapNotAvailable
// otherwise. Non-blocking; suitable for diagnostics commands like
// `beatsd doctor` that just want to know "would the cadence path work?".
func ProbeEventTap() error {
	if C.probeEventTap() != 0 {
		return ErrEventTapNotAvailable
	}
	return nil
}

// StartEventTap installs a CGEventTap that counts input events and returns
// (getAndReset, stop, nil) on success. The tap is passive
// (kCGEventTapOptionListenOnly) and only ever increments an atomic counter —
// it never reads keycodes, mouse coordinates, or any other event payload.
//
// Returns ErrEventTapNotAvailable if CGEventTapCreate refuses the request,
// which is the normal "no Accessibility permission" path. The collector
// loop already catches this and falls back to the 0.5 default cadence.
func StartEventTap() (getAndReset func() int64, stop func(), err error) {
	if C.startTap() != 0 {
		return nil, nil, ErrEventTapNotAvailable
	}

	// Drive the CFRunLoop on a dedicated OS thread. Calling C.runTapLoop on
	// any other goroutine is incorrect because CFRunLoopRun blocks forever
	// and cgo doesn't promise the caller a fixed thread.
	go func() {
		C.runTapLoop()
	}()

	getAndReset = func() int64 {
		return int64(C.getAndResetCount())
	}
	stop = func() {
		C.stopTap()
	}
	return getAndReset, stop, nil
}
