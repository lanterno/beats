// Tests for parseFlowSummary. Both FlowScreen and CoachScreen route
// /summary responses through this parser; the edge cases worth
// locking in are around the "no data" branches (count=0 → null,
// missing fields → 0, null map → null) and the rounding contract
// (avg/peak come back from the API as 0..1 doubles, the parser
// pre-rounds to integer percent points so widgets never have to do
// arithmetic).

import 'package:beats_companion/services/flow_summary.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('parseFlowSummary', () {
    test('returns null when the map itself is null', () {
      expect(parseFlowSummary(null), isNull);
    });

    test('returns null when count is 0 — never render "avg 0"', () {
      // Same rule the VS Code status bar follows: rendering "Beats 0"
      // early in the morning reads as "you're at zero" which is the
      // wrong signal. Suppress the headline until count > 0.
      final out = parseFlowSummary({
        'count': 0,
        'avg': 0,
        'peak': 0,
        'top_repo': null,
        'top_language': null,
        'top_bundle': null,
      });
      expect(out, isNull);
    });

    test('returns null when count is missing entirely', () {
      // Defensive — the API always sends count, but a future schema
      // change shouldn't crash older companions.
      expect(parseFlowSummary({'avg': 0.5, 'peak': 0.7}), isNull);
    });

    test('rounds avg + peak from 0..1 doubles to integer percent points', () {
      final out = parseFlowSummary({
        'count': 23,
        'avg': 0.674,
        'peak': 0.912,
      });
      expect(out, isNotNull);
      // 0.674 * 100 = 67.4 → 67. 0.912 * 100 = 91.2 → 91.
      expect(out!.avg, 67);
      expect(out.peak, 91);
      expect(out.count, 23);
    });

    test('handles ints sent in place of doubles (num.toDouble round-trip)', () {
      // Some JSON parsers materialize whole numbers as int even when
      // the schema says double. parseFlowSummary should accept both.
      final out = parseFlowSummary({'count': 1, 'avg': 1, 'peak': 0});
      expect(out!.avg, 100);
      expect(out.peak, 0);
    });

    test('extracts top_repo / top_language / top_bundle keys when present', () {
      final out = parseFlowSummary({
        'count': 5,
        'avg': 0.6,
        'peak': 0.8,
        'top_repo': {'key': '/Users/me/code/beats', 'avg': 0.7, 'count': 3},
        'top_language': {'key': 'go', 'avg': 0.7, 'count': 3},
        'top_bundle': {'key': 'com.microsoft.VSCode', 'avg': 0.7, 'count': 5},
      });
      expect(out!.topRepo, '/Users/me/code/beats');
      expect(out.topLanguage, 'go');
      expect(out.topBundle, 'com.microsoft.VSCode');
    });

    test('top_* fields default to null when the map is missing them', () {
      // No editor heartbeats → top_repo / top_language come back as
      // null on the wire; widgets render the headline without those
      // axes rather than crashing.
      final out = parseFlowSummary({
        'count': 5,
        'avg': 0.6,
        'peak': 0.8,
      });
      expect(out!.topRepo, isNull);
      expect(out.topLanguage, isNull);
      expect(out.topBundle, isNull);
    });
  });
}
