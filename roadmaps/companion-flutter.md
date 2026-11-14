# The companion on Flutter 3.50

**What it blocks:** Renovate's window_manager PR (#448), any Flutter bump
Renovate proposes for `companion/.fvmrc`, and upgrading the Homebrew Flutter
on a development machine. **What blocks it:** nothing but the work below.

## Why the companion is held on 3.47

On 2026-11-11 Flutter's stable channel moved from 3.47.9 (Dart 3.13) to
3.50.0 (Dart 3.14), and every Companion CI run failed from then on, on every
branch: `nativeapi` 0.5.2, which `tray_manager` ^0.8 locks, calls
`Isolate.create` and `runEventLoopSync`, experimental VM APIs that Dart 3.14
removed, while declaring `sdk: ^3.13.0`, so pub let 3.14 resolve it.
`nativeapi` 0.5.11 fixes it and requires Flutter 3.50; `tray_manager` 0.9 and
`window_manager` 0.7 are that line.

So, since #467, CI runs the Flutter in `companion/.fvmrc` (3.47.9) instead of
whatever stable is that day, and `companion/pubspec.yaml` admits
`>=3.47.0 <3.50.0` with a comment saying why. The lockfile, CI and a local
`pub get` now agree on one SDK.

## Work

One change, because the pieces cannot move apart: `window_manager` 0.7 needs
`nativeapi` ^0.6, which `tray_manager` ^0.8 conflicts with (that is #448's
version-solving failure), and `tray_manager` 0.9 needs Flutter 3.50.

1. Move `tray_manager` to ^0.9 and `window_manager` to ^0.7 together, on
   Flutter 3.50. `window_manager` 0.6 rewrote its API; the companion calls the
   old one in `companion/lib/main.dart` (`windowManager.ensureInitialized`,
   `waitUntilReadyToShow` with `WindowOptions`, `show`, `focus`),
   `lib/screens/settings_screen.dart` and `lib/screens/shell.dart`, and on
   3.47.9 #448's new API fails `flutter analyze`. Read the new signatures
   rather than trusting a green suite: the tray and window code is the part
   the tests mock.
2. Lift the bound in `companion/pubspec.yaml` (and its comment), set
   `companion/.fvmrc` to the 3.50 release, and regenerate `pubspec.lock`.
3. Build the macOS app (`build-macos` in `.github/workflows/companion.yml`)
   and run it: the menu bar icon and the window's show-on-launch are what the
   two plugins do, and no test draws them.
4. Upgrade the local Homebrew SDK in the same sitting, and change CLAUDE.md
   § *Testing Strategy*, which says the local SDK has to be a 3.47. Then
   delete this file and its row in roadmaps/README.md.

**Must not:** float CI back to `channel: stable`. The break was a floating
SDK under a locked dependency graph; `.fvmrc` is what keeps the two together,
and Renovate's fvm manager proposes the next bump as a PR.

## Found alongside, not part of it

Renovate's `flutter_local_notifications` 23 PR (#458) resolves on 3.47 but
fails a real test on 3.47.9, `start_sheet_test: a typed time reaches both
halves of the switch`. It is its own fix, whichever Flutter it lands on.
