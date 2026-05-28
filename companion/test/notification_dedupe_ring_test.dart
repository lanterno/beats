import 'package:flutter_test/flutter_test.dart';
import 'package:beats_companion/services/notification_dedupe_ring.dart';

void main() {
  group('appendBounded', () {
    test('appends a new id to the newest (end) position', () {
      expect(appendBounded(['a', 'b'], 'c', 10), ['a', 'b', 'c']);
    });

    test('appending to an empty list yields a single-element list', () {
      expect(appendBounded(const [], 'a', 10), ['a']);
    });

    test('re-appending an existing id moves it to newest, no duplicate', () {
      expect(appendBounded(['a', 'b', 'c'], 'a', 10), ['b', 'c', 'a']);
    });

    test('does not mutate the input list', () {
      final input = ['a', 'b'];
      appendBounded(input, 'c', 10);
      expect(input, ['a', 'b']);
    });

    test('evicts the oldest entries when over the cap', () {
      expect(appendBounded(['a', 'b', 'c'], 'd', 3), ['b', 'c', 'd']);
    });

    test('a full tick of ids stays within the cap, keeping the newest', () {
      var ids = <String>[];
      for (var i = 0; i < 100; i++) {
        ids = appendBounded(ids, 'e-$i', 64);
      }
      expect(ids.length, 64);
      expect(ids.first, 'e-36'); // 100 - 64
      expect(ids.last, 'e-99');
    });

    test('cap of zero retains nothing', () {
      expect(appendBounded(['a'], 'b', 0), isEmpty);
    });
  });
}
