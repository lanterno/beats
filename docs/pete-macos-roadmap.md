# Pete — macOS Roadmap

> Pete is the Mac surface of the Beats system. This roadmap is the
> Mac-only ambition: the things a desktop with a menu bar, a window
> server, a Focus engine, and a Continuity stack can do that no other
> platform can match.
>
> **Aesthetic:** Brutalist Luxury, applied to the OS. Ambient where the
> system invites it (menu bar, floating chip, Stand By), monastic
> elsewhere (no notification spam, no dock bounce, no chrome).

The work below assumes the cross-platform companion already covers
timer / flow / coach / health. Items here are macOS-native because they
*should* be, not because they were ported.

---

## I. Ambient presence

The timer should feel like part of the desk, not an app you open.

- ~~**Floating now-bar**~~ — *Cut. The menu-bar tray already shows
  elapsed time + project; a floating panel duplicated the signal at the
  cost of screen real estate.*
- **Dock badge** — minute counter on Pete's dock icon while running
  (`NSApp.dockTile.badgeLabel`). Resets to empty on stop. The minutes
  read like a wristwatch in your peripheral vision.
- **Menu-bar sparkline** — replace the static dot in the tray with a
  16-pixel-tall flow-score sparkline of the last 90 minutes, redrawn
  every 5 min. Tap → opens the Flow tab. Reuses `TrayIconRenderer` —
  add a sparkline mode that bakes a tiny PNG.
- **Stand By "Monastic Clock"** — when the Mac docks (Sequoia Stand By
  on supported Macs, plus an opt-in always-on full-screen on intel), a
  full-bleed brutalist clock face: HH:MM:SS in the same DM Serif /
  JetBrains Mono pairing as the timer screen, project dot pulsing in
  the corner. No bezels, no buttons. ESC exits.

## II. System-aware focus

Pete should know what the Mac is doing without asking.

- **Focus auto-engage** — when a timer starts, push a `Focus` filter
  via the Shortcuts intent surface (`SetFocusIntent`) keyed to the
  project: e.g. *Deep Work* for the engineering project, *Meeting* for
  calendar-driven sessions. Returns to *Personal* on stop. Permission-
  gated, off by default — but once on, it's the headline feature.
- **Frontmost-window suggestions** — every 60 s, sample the frontmost
  app + window title via `NSWorkspace.shared.frontmostApplication` and
  the Accessibility API. Match against project hints (linear.app →
  Linear project, github.com/<repo> → repo project). When a confident
  match runs > 8 min and no timer is active, the existing auto-timer
  notification fires — but with a *richer* card on macOS: app icon +
  window title + duration + Start button, rendered as a custom
  `UNNotificationContentExtension`.
- **Calendar-aware nudges** — read the user's default Calendar (no
  Beats integration needed if EventKit grants access) and:
  - 60 s before a meeting starts: offer "Pause and switch to Meeting?"
  - On meeting end: offer "Resume <previous project>?"
  - Match the meeting title against project names heuristically.
- **Screen Time delta** — at the end of every session, read Screen
  Time's per-app usage deltas (DeviceActivity API) for the session
  window and roll them into the post-stop sheet: *"You spent 38 min in
  Xcode, 4 min in Slack, 1 min in Twitter."* User can confirm or split.

## III. Hands-free input

Keyboard ≫ menu.

- **Global hotkeys** — `MASShortcut`-style configurable bindings for
  `Start last project` (`⌃⌥⌘P`), `Stop` (`⌃⌥⌘.`), `Swap project`
  (`⌃⌥⌘ ↹` opens a HUD picker), `Quick-capture note` (`⌃⌥⌘N` shows a
  one-line input that appends a tag/note to the running session).
  HUD picker is a borderless `NSPanel` with a `TextField` and a
  monospaced project list — same vocabulary as Raycast.
- **Spotlight / Raycast / Alfred provider** — register a CoreSpotlight
  domain *and* ship a Raycast extension. Typing `pete linear` starts
  a timer for the Linear project; `pete stop` stops; `pete note <text>`
  appends. Single binary entry: `pete-cli`, talks to the running
  app over a Unix socket so there's no double network round-trip.
- **Shortcuts.app actions** — expose the full timer + intentions API
  as `AppIntent`s: *Start Timer*, *Stop Timer*, *Get Current Project*,
  *Add Intention*, *Get Today Total*. Now any user can wire Pete into
  Stream Deck, Keyboard Maestro, or a homemade NFC tag on the desk.
- **Services menu** — selected text in any app → *Services › Pete ›
  Start timer with project name…* prefills the picker. Selected URL →
  if it matches a project hint, starts immediately.

## IV. Continuity & live presence

Pete should follow the user across their devices.

- **Live Activity bridge** — when the iPhone companion has a timer
  running, surface a Live Activity on the Mac's menu bar (Sonoma+'s
  iPhone-mirrored Live Activities). Conversely, when Pete starts a
  timer on the Mac, the iPhone Live Activity reflects it within
  seconds. One source of truth: the API; the bridge is just the
  Activity payload.
- **Handoff** — `NSUserActivity` advertised when a project view is
  visible. Open Pete on a second Mac signed into the same iCloud →
  Handoff icon in the dock; one click and the same project is loaded
  with the same running timer.
- **iCloud key-value store** — recent-projects list, post-stop tag
  history, custom hotkey bindings. Three Macs, one synced state. Token
  stays in Keychain (per-machine on purpose).

## V. Coach-on-Mac (Apple Intelligence)

The morning brief and evening review are a perfect surface for the
on-device LLM stack. All optional, gated behind a single *"Use Apple
Intelligence"* toggle.

- **Writing Tools on the post-stop note** — Rewrite / Proofread /
  Summarize buttons in the note sheet, calling
  `WritingToolsCoordinator`. The result is debounce-saved like the
  manual edit.
- **Genmoji project icons** — the project picker today shows colored
  dots. Let users pick or *generate* a Genmoji per project via
  `GenmojiKit`. Pete renders the Genmoji in the tray icon and floating
  now-bar.
- **Image Playground end-of-week postcard** — Friday evening, after the
  review, generate an Image Playground card themed on the week's
  dominant project / mood. Shareable as a wallpaper.
- **Live transcription for meeting sessions** — when a session is
  tagged `#meeting`, optionally start `SpeechAnalyzer` (on-device) and
  attach a transcript to the beat. Strictly opt-in per session; the
  transcript never leaves the device unless the user explicitly
  uploads it.

## VI. Distribution polish

The work that turns Pete from a sideloaded `.app` into something a
non-developer can install.

- **Developer ID signing + notarization** — fixes the keychain-ACL
  reset on every rebuild (the bug we hit during the rename). One-time
  Apple Developer enrollment + a `codesign` step in CI.
- **Sparkle auto-update channel** — release feed at
  `releases.beats.app/pete/appcast.xml`, signed with `EdDSA`. Updates
  land silently overnight; user sees a "What's changed" sheet on next
  launch.
- **Homebrew Cask** — `brew install --cask pete` once notarization is
  live. Mirrors the `beatsd` formula already in the homebrew-tap doc.
- **App icon refresh** — proper macOS squircle, dark-mode variant, +
  template menu-bar icon (vector PDF). Today the menu bar uses a
  rasterized PNG that doesn't recolor in dark mode.
- **Crash + perf telemetry** — `os.signpost` instrumentation around
  startup, keychain access, and the foreground poller, surfaced via
  Instruments. Crash logs collected via `MetricKit` (opt-in).

---

## Cut for now

Things that sound cool but don't earn their keep yet.

- **Touch Bar** — almost no Macs ship it. Skip.
- **Widget Center widgets** — duplicates iOS widgets without enough
  unique macOS surface. Reconsider once iOS widgets are real (see the
  cross-platform roadmap).
- **Stage Manager-aware layouts** — interesting but no clean API; what
  signal would Pete take from it?
- **Sherlocking risk** — if Apple ships a first-party Time Tracker in a
  future Health/Productivity bundle, half of this becomes redundant.
  Build the things that depend on Beats data (flow score, coach,
  intentions) first; the timer-as-timer features second.

---

## Sequencing

A sane order if you want to pull from the top:

1. **Distribution polish** (signing → Sparkle → Cask). Unblocks every
   user-facing release after.
2. **Dock badge** + **menu-bar sparkline** + **Monastic Clock**. The
   menu-bar surface carries the running state; the dock badge gives a
   peripheral minute counter; Monastic is the dessert mode for docked
   displays.
3. **Global hotkeys** + **CLI/Spotlight provider**. Power-user retention
   loop.
4. **Focus auto-engage** + **frontmost-window suggestions**. The thing
   no other time tracker does well.
5. **Live Activity bridge** + **Handoff**. Once the iPhone companion
   has Live Activities, the Mac side is a few hours of work.
6. **Apple Intelligence layer**. Last because it's the most
   cosmetically impressive but the least load-bearing.

Stand By, Genmoji, and the Image Playground postcard are dessert —
ship after the main course.
