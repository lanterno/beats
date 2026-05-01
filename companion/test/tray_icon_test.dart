// Tests for the pure helpers in tray_icon.dart. The actual PNG
// rasterization is intentionally NOT tested — that path requires
// path_provider + a Flutter binding that has a real renderer, which
// is too much ceremony for color-string normalization. These tests
// cover the inputs that come from upstream JSON (project colors)
// and could plausibly drift.

import 'dart:ui' as ui;

import 'package:beats_companion/services/tray_icon.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('trayHexFromRgb', () {
    test('encodes a normal RGB triple as six uppercase-friendly hex chars', () {
      // Lowercase output is fine here — the renderer normalizes via
      // toUpperCase before keying the cache.
      expect(trayHexFromRgb([255, 128, 0]), 'ff8000');
    });

    test('zero-pads single-digit components', () {
      // Defensive against the formatter dropping leading zeros — a
      // (5, 0, 5) triple has to come out as "050005" not "5005".
      expect(trayHexFromRgb([5, 0, 5]), '050005');
    });

    test('returns null when the list is missing', () {
      expect(trayHexFromRgb(null), isNull);
    });

    test('returns null when the list has fewer than 3 elements', () {
      // Defensive — older/buggy upstream JSON could send [r, g] and
      // we'd otherwise panic on rgb[2].
      expect(trayHexFromRgb([255]), isNull);
      expect(trayHexFromRgb([255, 128]), isNull);
      expect(trayHexFromRgb(<int>[]), isNull);
    });

    test('clamps out-of-range values into 00..ff so toRadixString never overflows', () {
      // Upstream might send 256 or negative due to a parse glitch.
      // Clamp instead of throw — the tray icon is a low-stakes
      // visualization and a panic kills the menu bar permanently.
      expect(trayHexFromRgb([256, -1, 999]), 'ff00ff');
    });

    test('reads only the first three elements when more are passed', () {
      // Some color formats (RGBA) come with an alpha. Drop it
      // silently — the tray icon always renders fully opaque.
      expect(trayHexFromRgb([1, 2, 3, 4]), '010203');
    });
  });

  group('trayParseHex', () {
    test('parses a six-char hex without #', () {
      expect(trayParseHex('ff8000'), const ui.Color(0xFFFF8000));
    });

    test('strips a leading # before parsing', () {
      // Project colors from JSON sometimes arrive as "#ff8000".
      expect(trayParseHex('#ff8000'), const ui.Color(0xFFFF8000));
    });

    test('falls back to neutral gray on a parse error', () {
      // Empty string, garbage, anything that isn't a hex int — the
      // tray needs SOMETHING to render. Better a gray dot than a
      // crash + blank menu bar.
      expect(trayParseHex(''), const ui.Color(0xFF7A7A7A));
      expect(trayParseHex('not-a-hex'), const ui.Color(0xFF7A7A7A));
    });

    test('always sets full alpha (0xFF) on the high byte', () {
      // Even when the input could be interpreted as ARGB (e.g.
      // "00ff8000"), we OR in 0xFF000000 so the icon is never
      // half-transparent on a desktop that respects alpha.
      final c = trayParseHex('00ff8000');
      expect(c.toARGB32() >> 24 & 0xFF, 0xFF);
    });
  });
}
