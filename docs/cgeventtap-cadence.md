# CGEventTap Cadence Tracking

> **Status: shipped.** `daemon/internal/collector/cadence_darwin.go` implements the real CGEventTap; `daemon/internal/collector/cadence.go` is the non-darwin fallback. The collector loop already handled the `ErrEventTapNotAvailable` path, so no other code changed.

Replaces the cadence stub with real input event counting via macOS CGEventTap for accurate Flow Score cadence scoring.

## Why

The Flow Score's `cadence_score` component (40% of the total) currently defaults to 0.5 because the event tap is stubbed. With real input event counting, the daemon can distinguish between active coding (high cadence, high score) and passive reading (low cadence, lower score). This makes the Flow Score significantly more accurate.

## How It Works

`CGEventTapCreate` installs a passive event listener at the HID (Human Interface Device) level. It counts key-down, mouse-move, and scroll events without capturing keycodes, mouse positions, or any content. The count is atomically read and reset every 5 seconds by the collector loop.

## Prerequisites

- **macOS Accessibility permission**: the user must grant the `beatsd` binary (or Terminal.app if running from terminal) access in System Settings > Privacy & Security > Accessibility.
- Without this permission, `CGEventTapCreate` returns NULL and the daemon falls back to the 0.5 stub. The daemon already handles this gracefully.

## Implementation

### File: `daemon/internal/collector/cadence_darwin.go`

```go
//go:build darwin

package collector

/*
#cgo CFLAGS: -x objective-c
#cgo LDFLAGS: -framework ApplicationServices -framework CoreFoundation

#include <ApplicationServices/ApplicationServices.h>
#include <stdint.h>

static volatile int64_t eventCount = 0;
static CFMachPortRef tapRef = NULL;
static CFRunLoopSourceRef sourceRef = NULL;
static CFRunLoopRef tapRunLoop = NULL;

CGEventRef tapCallback(CGEventTapProxy proxy, CGEventType type,
                       CGEventRef event, void *refcon) {
    __sync_add_and_fetch(&eventCount, 1);
    return event;
}

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
        return -1;  // No accessibility permission
    }

    sourceRef = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tapRef, 0);
    return 0;
}

static void runTapLoop() {
    tapRunLoop = CFRunLoopGetCurrent();
    CFRunLoopAddSource(tapRunLoop, sourceRef, kCFRunLoopCommonModes);
    CGEventTapEnable(tapRef, true);
    CFRunLoopRun();
}

static void stopTap() {
    if (tapRunLoop != NULL) {
        CFRunLoopStop(tapRunLoop);
    }
    if (tapRef != NULL) {
        CGEventTapEnable(tapRef, false);
        CFRelease(tapRef);
        tapRef = NULL;
    }
    if (sourceRef != NULL) {
        CFRelease(sourceRef);
        sourceRef = NULL;
    }
}

static int64_t getAndResetCount() {
    return __sync_lock_test_and_set(&eventCount, 0);
}
*/
import "C"

import (
    "errors"
    "sync"
)

var tapOnce sync.Once

func StartEventTap() (getAndReset func() int64, stop func(), err error) {
    if C.startTap() != 0 {
        return nil, nil, errors.New("CGEventTapCreate failed — grant Accessibility permission")
    }

    // Run the CFRunLoop on a background goroutine
    go C.runTapLoop()

    getAndReset = func() int64 {
        return int64(C.getAndResetCount())
    }
    stop = func() {
        C.stopTap()
    }
    return getAndReset, stop, nil
}
```

### File: `daemon/internal/collector/cadence.go` (updated)

The current file becomes the non-darwin fallback:

```go
//go:build !darwin

package collector

import "errors"

var ErrEventTapNotAvailable = errors.New("event tap not available on this platform")

func StartEventTap() (getAndReset func() int64, stop func(), err error) {
    return nil, nil, ErrEventTapNotAvailable
}
```

### Build tag split

- `cadence_darwin.go` — `//go:build darwin` — real CGEventTap
- `cadence.go` — `//go:build !darwin` — stub fallback

Both export the same `StartEventTap()` signature. The collector loop (`loop.go`) doesn't change.

## Privacy Guarantees

The event tap callback:
- Receives `CGEventRef` but only increments a counter
- Does NOT read `CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)` — no keycodes
- Does NOT read mouse coordinates
- Uses `kCGEventTapOptionListenOnly` — cannot modify or block events
- The counter is read and reset every 5 seconds; individual event timestamps are not recorded

## Testing

1. **Unit test**: mock the C functions is impractical. Instead, test the Go wrapper by checking that `StartEventTap` returns non-nil functions on macOS (or `ErrEventTapNotAvailable` without Accessibility permission).
2. **Manual test**: run `beatsd --dry-run run`, verify cadence_score varies with typing activity.
3. **Privacy audit**: run `beatsd --dry-run run > /tmp/flow.log` for 1 hour, grep the log for any content — there should be none, only numeric scores and bundle IDs.

## Onboarding UX

When the daemon starts and `CGEventTapCreate` fails:
```
warning: input event tap not available — cadence will default to 0.5
To enable accurate cadence tracking:
  System Settings > Privacy & Security > Accessibility > enable "beatsd"
```

The daemon continues to work without it — cadence is 40% of the score, but coherence (40%) and category fit (20%) still provide useful signal.

`beatsd doctor` runs the same check non-fatally and prints a one-line status alongside the other prerequisites (device token, API reachability, editor port). Useful for first-run setup and for triaging "why isn't my flow score moving?" — the doctor row will read `stub fallback` instead of `active (real input counting)` if the permission isn't granted.

## Risks

| Risk | Mitigation |
|------|------------|
| User denies Accessibility permission | Graceful degradation — daemon works, cadence defaults to 0.5 |
| macOS revokes permission on binary update | Homebrew installs to the same path; permission persists. Ad-hoc signed binaries may lose it |
| Event tap disabled by MDM | Same as permission denied — stub fallback |
| CPU overhead from event counting | The callback is a single atomic increment — negligible |
