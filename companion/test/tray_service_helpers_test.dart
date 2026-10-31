// Tests for the pure helpers extracted from TrayService —
// trayHexToRgb (color decoding) and formatTrayElapsed (timer
// label). The actual menu-bar rendering is intentionally not
// tested; that requires SystemTray + a desktop binding which is
// too much ceremony for color/timer-string normalization.

import 'package:beats_companion/services/tray_service.dart';
import 'package:beats_companion/state/prefs.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('trayHexToRgb', () {
    test('decodes a valid six-char hex (no leading #)', () {
      expect(trayHexToRgb('FF8000'), [255, 128, 0]);
    });

    test('strips a leading # before decoding', () {
      // Project colors arrive as either "ff8000" or "#ff8000"
      // depending on the upstream serializer; both should work.
      expect(trayHexToRgb('#FF8000'), [255, 128, 0]);
    });

    test('falls back to neutral gray for null', () {
      // The tray icon needs SOMETHING to render — a panic kills
      // the menu bar permanently, a gray dot is a soft signal.
      expect(trayHexToRgb(null), [122, 122, 122]);
    });

    test('falls back to neutral gray for empty string', () {
      expect(trayHexToRgb(''), [122, 122, 122]);
    });

    test('falls back to neutral gray for wrong-length hex', () {
      // "fff" (three-char hex shorthand) isn't supported — the
      // tray icon needs full RGB precision. Defensive: fall back
      // rather than mis-render a half-decoded color.
      expect(trayHexToRgb('fff'), [122, 122, 122]);
      expect(trayHexToRgb('ff80000'), [122, 122, 122]);
      expect(trayHexToRgb('ff'), [122, 122, 122]);
    });

    test('falls back component-by-component on partial hex parse failure', () {
      // "GG" isn't valid hex; the parse fails and the default
      // component (122) lands instead. The other valid components
      // still decode correctly. Locks in the per-component fallback
      // rather than an all-or-nothing rejection.
      expect(trayHexToRgb('GG8000'), [122, 128, 0]);
    });

    test('reads lowercase hex too', () {
      // The renderer uppercases via toUpperCase before keying its
      // cache, so the input case shouldn't matter here. Lock it in.
      expect(trayHexToRgb('ff8000'), [255, 128, 0]);
    });
  });

  group('formatTrayElapsed', () {
    test('zero duration renders as 00:00', () {
      expect(formatTrayElapsed(Duration.zero), '00:00');
    });

    test('sub-minute renders as MM:SS with zero padding on seconds', () {
      expect(formatTrayElapsed(const Duration(seconds: 7)), '00:07');
      expect(formatTrayElapsed(const Duration(seconds: 42)), '00:42');
    });

    test('sub-hour renders as MM:SS with zero padding on both sides', () {
      // 5 minutes 3 seconds → "05:03", not "5:3" or "5:03".
      expect(formatTrayElapsed(const Duration(minutes: 5, seconds: 3)), '05:03');
      expect(formatTrayElapsed(const Duration(minutes: 59, seconds: 59)), '59:59');
    });

    test('crosses to Hh MMm at exactly one hour', () {
      // 60:00 in MM:SS would look weird in the menu bar, so we
      // switch to "1h 00m" at the hour boundary. Lock it in.
      expect(formatTrayElapsed(const Duration(hours: 1)), '1h 00m');
    });

    test('multi-hour pads the minutes, not the hours', () {
      // 12 hours 5 minutes → "12h 05m", not "12h 5m".
      expect(formatTrayElapsed(const Duration(hours: 12, minutes: 5)), '12h 05m');
    });

    test('clamps negative durations to 00:00', () {
      // Defensive — a clock skew between client and server timer
      // start could in theory produce a negative elapsed. Don't
      // render "-3:00" in the menu bar.
      expect(formatTrayElapsed(const Duration(seconds: -90)), '00:00');
    });
  });

  group('flowScoresFromWindows', () {
    test('reads the API flow_score field and coerces num to double', () {
      final scores = flowScoresFromWindows([
        {'flow_score': 0.25},
        {'flow_score': 1}, // int coerced to double
      ]);
      expect(scores, [0.25, 1.0]);
    });

    test('regression: a window keyed only as "score" yields nothing', () {
      // The tray previously read w['score'], but the API emits
      // w['flow_score'] — so the sparkline buffer was always empty and the
      // menu-bar sparkline never rendered. Pin the correct key.
      expect(flowScoresFromWindows([
        {'score': 0.8},
      ]), isEmpty);
    });

    test('clamps out-of-range scores into [0,1]', () {
      expect(flowScoresFromWindows([
        {'flow_score': 1.5},
        {'flow_score': -0.3},
      ]), [1.0, 0.0]);
    });

    test('skips missing / null / non-numeric scores, keeps the rest', () {
      final scores = flowScoresFromWindows([
        {'flow_score': 0.5},
        {'other': 1},
        {'flow_score': null},
        {'flow_score': 'x'},
        {'flow_score': 0.9},
      ]);
      expect(scores, [0.5, 0.9]);
    });

    test('empty input returns empty', () {
      expect(flowScoresFromWindows([]), isEmpty);
    });
  });

  group('dockBadgeForElapsed', () {
    test('running shows whole elapsed minutes', () {
      expect(dockBadgeForElapsed(const Duration(minutes: 5, seconds: 40), running: true), '5');
      expect(dockBadgeForElapsed(Duration.zero, running: true), '0');
      expect(dockBadgeForElapsed(const Duration(minutes: 90), running: true), '90');
    });

    test('idle (not running) clears the badge', () {
      expect(dockBadgeForElapsed(null, running: false), isNull);
      // Even a stray elapsed must not show a badge when not running.
      expect(dockBadgeForElapsed(const Duration(minutes: 5), running: false), isNull);
    });

    test('running with null elapsed clears the badge', () {
      expect(dockBadgeForElapsed(null, running: true), isNull);
    });

    test('negative elapsed (clock skew) clamps to "0"', () {
      expect(dockBadgeForElapsed(const Duration(seconds: -30), running: true), '0');
    });
  });

  group('menuBarTitle', () {
    const elapsed = Duration(hours: 1, minutes: 24, seconds: 7);

    test('follows what Settings says the item shows', () {
      expect(menuBarTitle(MenuBarShows.timeAndProject, project: 'Northwind', elapsed: elapsed),
          '1:24 Northwind');
      expect(menuBarTitle(MenuBarShows.time, project: 'Northwind', elapsed: elapsed), '1:24');
      expect(menuBarTitle(MenuBarShows.icon, project: 'Northwind', elapsed: elapsed), '');
    });

    test('is empty while nothing runs', () {
      expect(menuBarTitle(MenuBarShows.timeAndProject), '');
    });
  });

  // The tray's label off macOS. It follows the same Settings preference the
  // Mac's status item does — which it did not before: _tick formatted the
  // tray's title one way and decided whether to send it from the Mac's,
  // so the preference did nothing there and the MM:SS only moved when the
  // Mac's minute-granularity title changed.
  group('trayTitle', () {
    const elapsed = Duration(minutes: 24, seconds: 17);

    test('follows what Settings says the item shows', () {
      expect(trayTitle(MenuBarShows.timeAndProject, project: 'Northwind', elapsed: elapsed),
          '24:17  Northwind');
      expect(trayTitle(MenuBarShows.time, project: 'Northwind', elapsed: elapsed), '24:17');
      expect(trayTitle(MenuBarShows.icon, project: 'Northwind', elapsed: elapsed), isNull);
    });

    test('is null while nothing runs, which is what clears the label', () {
      expect(trayTitle(MenuBarShows.timeAndProject), isNull);
    });

    test('changes with the second, so the stopwatch ticks', () {
      // The bug this helper exists to fix: a tray title that only moved
      // when the Mac's "24m" changed showed the same seconds for a minute.
      final a = trayTitle(MenuBarShows.time, project: 'N', elapsed: elapsed);
      final b = trayTitle(MenuBarShows.time,
          project: 'N', elapsed: elapsed + const Duration(seconds: 1));
      expect(a, isNot(b));
    });
  });
}
