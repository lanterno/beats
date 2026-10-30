import 'dart:convert';

import 'package:beats_companion/theme/sky.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

/// Zen Maru Gothic draws the em dash as the full-width Japanese bar, so body
/// text takes that one character from the LatinDash face (#324). A
/// family name that drifts between pubspec.yaml and sky.dart, a face left out
/// of the bundle or cut with more than the dash would all fail silently: the
/// text still draws, from the wrong face.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // `flutter test` does not load the app's fonts; load them the way the app
  // would, from the manifest pubspec.yaml's `fonts:` section becomes.
  setUpAll(() async {
    final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
    for (final family in manifest.cast<Map<String, dynamic>>()) {
      final loader = FontLoader(family['family'] as String);
      for (final font in (family['fonts'] as List).cast<Map<String, dynamic>>()) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
  });

  double width(String text, TextStyle style) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout();
    final width = painter.width;
    painter.dispose();
    return width;
  }

  test('body text takes the em dash from the Latin face and nothing else', () {
    final theme = buildSkyTheme(SkyPalette.afternoon, Brightness.light);
    // Zen Maru is fetched at run time, so here the rest falls through to the
    // test font, the one an unstyled TextStyle gets.
    const plain = TextStyle(fontSize: 100);
    for (final body in [SkyType.body(100), theme.textTheme.bodyMedium!.copyWith(fontSize: 100)]) {
      // M PLUS Rounded 1c's em dash is 946 units of 1000.
      expect(width('\u{2014}', body), closeTo(94.6, 0.1));
      // The en dash among them: Zen Maru's is already a Latin one.
      for (final other in ['\u{2013}', '-', 'a', 'M', '1']) {
        expect(width(other, body), width(other, plain), reason: other);
      }
    }
  });
}
