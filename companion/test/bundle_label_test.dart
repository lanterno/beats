// Cross-language parity check: each assertion mirrors a case in the
// web's bundleLabel.test.ts. A user looking at the web FlowHeadline
// and the companion FlowScreen should see the same friendly app
// names — these tests guard against the two implementations
// drifting.

import 'package:beats_companion/services/bundle_label.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('shortBundleLabel', () {
    test('returns the human-friendly label for known apps', () {
      expect(shortBundleLabel('com.microsoft.VSCode'), 'VS Code');
      expect(shortBundleLabel('com.apple.dt.Xcode'), 'Xcode');
      expect(shortBundleLabel('com.jetbrains.goland'), 'GoLand');
    });

    test('falls back to the trailing reverse-DNS segment for unknown apps', () {
      expect(shortBundleLabel('com.todesktop.230313mzl4w4u92'), '230313mzl4w4u92');
      expect(shortBundleLabel('com.example.MyApp'), 'MyApp');
    });

    test('returns the input unchanged when there are no dots', () {
      expect(shortBundleLabel('standalone'), 'standalone');
    });

    test('returns empty string for empty input', () {
      expect(shortBundleLabel(''), '');
    });
  });
}
