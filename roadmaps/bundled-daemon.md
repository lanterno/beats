# The daemon inside the desktop app

One download instead of two. Today a desktop user who wants flow scores installs
the LifePete app and, separately, `beatsd` (Homebrew on the Mac, a release
archive elsewhere), then pairs each on its own. Each shows up as a device of its
own in Settings. This plan ships `beatsd` inside the app on macOS, Windows
and Linux, started by the app, paired by the app, and off until the person turns
it on.

**What blocks it, per platform:**

- **macOS: Developer ID signing, #300** (`needs-paid-credentials`). The daemon
  needs the Accessibility permission for typing rhythm
  (`daemon/internal/collector/cadence_darwin.go`), and macOS keeps that grant
  against the binary's code signature. The app is ad-hoc signed today
  (`CODE_SIGN_IDENTITY = "-"` in `companion/macos/Runner.xcodeproj`), so every
  update would be a new program: the grant would be lost and asked for again,
  in a prompt naming `beatsd` rather than LifePete. That is worse than the
  Homebrew install it replaces. Everything in *Work* up to the macOS release
  can be built before #300; shipping it to anyone waits for it.
- **Windows and Linux: there is no installer to put it in.** The companion
  builds for both, but nothing ships them (companion/README.md § Platforms:
  "compile but tray-icon support is best-effort"). Bundling there comes with,
  or after, the first installer on each.

Nothing on the API changes. A device token reaches the same routes whichever
binary holds it (`DEVICE_ALLOWED_PREFIXES` in `api/src/server.py` has no kind
of device), so the app and its daemon can share one.

---

## What is there now

- **`beatsd` runs on its own** as `beatsd run`, under `brew services` on the
  Mac (`HomebrewFormula/`). It is built per platform by
  `.github/workflows/release-daemon.yml`. Darwin is built with cgo, which
  `cadence_darwin.go` needs; Windows and Linux are built without it. No build
  sets `-H windowsgui`.
- **It reads its own config and token**: `~/.config/beats/daemon.toml` for the
  API's address (`daemon/internal/config/config.go`), and the OS keychain
  under the service `beats-daemon` (`daemon/internal/pair/pair.go`, through
  `go-keyring`). The app keeps its token elsewhere: under
  `beats_device_token` through `flutter_secure_storage`
  (`companion/lib/services/token_storage.dart`), and its API address in
  `shared_preferences`.
- **It serves `127.0.0.1:37499`** for the VS Code extension's heartbeats
  (`daemon/internal/editor/listener.go`). `/health` there answers with the
  daemon's version, and `beatsd doctor` uses it to tell its own daemon from
  something else holding the port. A second daemon cannot bind it.
- **It raises its own notifications.** A drift alert fires the moment a
  distraction crosses 30 seconds, and a timer suggestion fires when a streak
  of flow has no timer. Both go through `daemon/internal/notify`: `osascript`
  on the Mac, which macOS files under *Script Editor*; `notify-send` on Linux;
  a PowerShell toast on Windows. The app separately polls
  `/api/signals/recent-drift` every five minutes and raises drift again
  (`companion/lib/services/notification_poller.dart`). A drift reaches the
  API only when it ends (`shield.go` emits on leaving the app), so the poll
  cannot stand in for the alert at the threshold.
- **The app already registers itself with launchd** for opening at login,
  through `SMAppService.mainApp` (`companion/macos/Runner/MacAmbientBridge.swift`).
  The same API registers a helper agent.

## How it runs on each platform

### macOS

- **Where it lives.** `LifePete.app/Contents/MacOS/beatsd` is one universal
  binary: arm64 and amd64 are each built with cgo, then joined with `lipo`. It
  is built in the companion's macOS build, which runs on a macOS runner
  already. The binary is signed with the app's identity and hardened runtime,
  because notarization refuses a bundle with anything unsigned inside.
- **How it starts.** A plist in `Contents/Library/LaunchAgents/` names the
  binary with `BundleProgram`, passes `run` and sets `KeepAlive`. The app
  registers it with `SMAppService.agent(plistName:)` when the setting is turned
  on, and unregisters it when it is turned off. It then appears in System
  Settings → General → Login Items under LifePete's name, and launchd keeps it
  running whether or not the window is open.
- **After an update** (Sparkle, #302) the agent keeps running the old binary
  until it restarts. The app compares its own version with the one `/health`
  reports and restarts the agent when they differ.
- **On the command line.** Raycast, Spotlight and Shortcuts call `beatsd`
  (#306). An *Install command-line tool* button in Settings links
  `/usr/local/bin/beatsd` to the copy in the bundle, the way VS Code installs
  `code`.

### Windows

- **Where it lives.** It sits beside `beats_companion.exe`, copied there by an
  `install()` in `companion/windows/runner/CMakeLists.txt`. It is built as the
  release builds it (`CGO_ENABLED=0`), plus `-H windowsgui`, so that no console
  window opens at every sign-in.
- **How it starts.** When the setting is turned on, the app writes a value under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, and it deletes the value
  when the setting is turned off. This needs no administrator rights, and
  removing it leaves nothing behind.
- **Typing rhythm** comes from Raw Input, which needs no permission.
- **Updating.** Windows will not replace a running `.exe`. Whatever updates the
  app (the installer, or the app before handing over to it) stops the daemon
  first, and starts it again after.
- **Signing.** An unsigned background process that watches the foreground
  window and raw input is what antivirus heuristics flag, on top of
  SmartScreen's warning for the installer. It needs an Authenticode
  certificate. Nothing is filed for that yet; it is step 5 below.

### Linux

- **Where it lives.** It goes in the Flutter bundle, through
  `companion/linux/CMakeLists.txt`.
- **How it starts.** An XDG autostart entry (`~/.config/autostart/`), written
  when the setting is turned on. A systemd user unit is the wrong fit: it often
  starts without `DISPLAY` or `WAYLAND_DISPLAY`, and every signal the daemon
  reads lives in the graphical session.
- **What it depends on.** It finds the frontmost app with `xdotool`/`xprop`, or
  `swaymsg` on sway, and idle time with `xprintidle` (daemon/README.md
  § Platform support). The package declares these as dependencies. On GNOME
  and KDE under Wayland none of them answers. `beatsd doctor`'s *Desktop
  signal sources* check already detects this; Settings shows its result rather
  than letting the daemon publish a flow score built on nothing. Typing rhythm
  has no source on Linux and falls back to 0.5.
- **Which package.** A `.deb`, `.rpm` or AppImage. In a Flatpak or Snap the
  sandbox hides other apps' windows, so a daemon inside one would see nothing;
  there it stays a separate install.

## Three decisions to make first

1. **One device or two.** The recommendation is one: the device is the machine.
   Revoking "this Mac" in the web's Settings should stop the app and its daemon
   together, and both already reach the same routes. That leaves the question
   of how the token crosses from the app to the daemon:
   - A keychain item that both read works on the Mac only if both are signed
     into one access group, which needs #300. Otherwise, reading an item another
     binary wrote raises a prompt.
   - A cross-platform alternative needs no signing: the app runs
     `beatsd pair` once, as a child process, handing it the token and the API's
     address on stdin. The daemon stores them where it always does. Unpairing
     the app then runs `beatsd unpair` the same way.
2. **Who raises the daemon's notifications.** Inside the app, the app should
   raise them. They would then appear under LifePete's name, follow the
   switches the person already has (`driftOn`, `suggestOn` and `holdingInFlow`
   in `companion/lib/state/prefs.dart`), and stop the double drift alert from
   the daemon and the poll. The poll arrives too late for that job (see above),
   so the daemon needs a local channel to the app. The candidates are the app
   reading pending alerts from the listener on `127.0.0.1:37499`, or the
   daemon calling the app. Either way, the daemon gains a setting that hands
   its alerts over instead of raising them.
3. **When another `beatsd` already runs**, whether from `brew services` or by
   hand. The recommendation: the app's copy stands aside, and Settings says
   which daemon is in use. The app never stops one it did not start. The Cask
   (#303) does not depend on the formula, and the formula stays for anyone
   who wants the daemon without the app.

## What must not happen

- **Installing the app must not start the daemon.** The daemon reads which app
  is in front, how long the machine has been idle and, on Mac and Windows, the
  rhythm of typing. A timer app does none of that. The daemon stays off until
  the person turns it on in Settings, next to a sentence saying what it reads
  and what it never does: no keys, no mouse positions, no window titles, no
  file paths beyond the workspace root (daemon/README.md § What gets
  collected). Accessibility is asked for at that moment, not at launch.
  PRIVACY.md says so before the release that adds it; its page has no section
  for the desktop app today.
- **Two daemons on one machine.** They would compete for 37499 and post every
  flow window twice.
- **The token anywhere another process or a backup can read it.** That rules
  out argv (`ps` shows it), an environment variable written into a plist, a
  unit file or a Run key, and any file of its own. It goes on stdin or into a
  keychain.
- **A macOS bundle shipped ad-hoc signed.** See the first screen.
- **A daemon in the bundle built from another commit than the app.** It is built
  in the same job from the same checkout, so the commit `beatsd version` names
  is the app's.
- **Dropping the Homebrew formula,** or the release archives. Linux servers,
  people who only want the CLI, and anyone who prefers to run the daemon
  themselves still install it on its own.

## Work

1. **Decide the three questions above** and write the answers here, in place of
   the recommendations.
2. **Daemon changes that every platform needs:**
   - `beatsd pair` taking a token and API address on stdin (if decision 1 goes
     that way);
   - a setting that hands alerts to the app instead of raising them;
   - a `-H windowsgui` build for the bundle.

   Each goes in its own commit with its tests.
3. **macOS.** Build, `lipo`, embed and sign `beatsd` in the companion's macOS
   build. Add the agent plist and its `SMAppService` registration, and the
   Settings switch: off by default, with its sentence, then the Accessibility
   step. Restart the agent after an update, stand aside for another daemon,
   and add *Install command-line tool*. Released once #300 lands, with
   PRIVACY.md, companion/README.md, daemon/README.md and
   `HomebrewFormula/README.md`, whose *Notes* then name the bundled copy as
   the other way to get the daemon on a Mac.
4. **Linux,** with its first package: embed the binary, write the autostart
   entry, declare the dependencies, and show the signal-sources check in
   Settings.
5. **Windows,** with its first installer: embed the binary, write the Run key,
   stop the daemon before updating, and get an Authenticode certificate for
   the app and the daemon both. That certificate needs a paid account, as #300
   does on the Mac.
6. **When each platform ships,** its part of this file moves to `docs/` and is
   deleted here (roadmaps/README.md § When something ships).
