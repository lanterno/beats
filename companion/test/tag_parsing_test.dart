import 'package:flutter_test/flutter_test.dart';
import 'package:beats_companion/services/tag_parsing.dart';

void main() {
  group('parseTagsInput', () {
    test('returns empty list for empty / whitespace-only input', () {
      expect(parseTagsInput(''), isEmpty);
      expect(parseTagsInput('   '), isEmpty);
      expect(parseTagsInput('\t\n  '), isEmpty);
    });

    test('splits on commas', () {
      expect(parseTagsInput('focus,deep,coding'), ['focus', 'deep', 'coding']);
    });

    test('splits on whitespace', () {
      expect(parseTagsInput('focus deep coding'), ['focus', 'deep', 'coding']);
    });

    test('handles mixed separators', () {
      expect(
        parseTagsInput('focus, deep coding,  refactor '),
        ['focus', 'deep', 'coding', 'refactor'],
      );
    });

    test('lowercases', () {
      expect(parseTagsInput('Focus DEEP'), ['focus', 'deep']);
    });

    test('dedupes — same tag twice in input collapses to one', () {
      expect(parseTagsInput('focus, focus, FOCUS'), ['focus']);
    });

    test('preserves first-seen order for distinct tags', () {
      // "deep" appears after "focus" in input, "refactor" last — order
      // sticks even though the implementation routes through a Set.
      expect(parseTagsInput('focus deep refactor'), ['focus', 'deep', 'refactor']);
    });

    test('drops empty pieces from runs of separators', () {
      expect(parseTagsInput(',,,focus,,,deep,,'), ['focus', 'deep']);
    });
  });

  group('mergeTags', () {
    test('returns empty when both inputs are empty', () {
      expect(mergeTags(chips: [], typed: []), isEmpty);
    });

    test('chips alone come through normalized', () {
      expect(
        mergeTags(chips: ['Focus', '  deep  '], typed: []),
        ['focus', 'deep'],
      );
    });

    test('typed alone come through normalized', () {
      expect(mergeTags(chips: [], typed: ['focus', 'deep']), ['focus', 'deep']);
    });

    test('chips come first, then new typed tags appended', () {
      expect(
        mergeTags(chips: ['focus'], typed: ['refactor', 'pairing']),
        ['focus', 'refactor', 'pairing'],
      );
    });

    test('a chip and a typed tag with the same value collapse to one', () {
      // The user might tap the "focus" chip AND retype it. Saving
      // should not produce ["focus", "focus"].
      expect(
        mergeTags(chips: ['focus'], typed: ['focus']),
        ['focus'],
      );
    });

    test('case differences across chips and typed are normalized away', () {
      expect(
        mergeTags(chips: ['Focus'], typed: ['FOCUS']),
        ['focus'],
      );
    });

    test('empty / whitespace entries are dropped from both sides', () {
      expect(
        mergeTags(chips: ['', '   ', 'focus'], typed: ['', 'deep', '\t']),
        ['focus', 'deep'],
      );
    });
  });
}
