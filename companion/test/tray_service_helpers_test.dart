// Tests for the pure helpers extracted from TrayService —
// trayHexToRgb (color decoding) and formatTrayElapsed (timer
// label). The actual menu-bar rendering is intentionally not
// tested; that requires SystemTray + a desktop binding which is
// too much ceremony for color/timer-string normalization.

import 'package:beats_companion/services/tray_service.dart';
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
}
