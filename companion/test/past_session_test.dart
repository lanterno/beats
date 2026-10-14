import 'package:beats_companion/services/past_session.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime(2026, 10, 14, 15, 0);
  DateTime at(int h, [int m = 0]) => DateTime(2026, 10, 14, h, m);

  group('pastSessionProblem', () {
    test('a past hour with nothing else on it is fine', () {
      expect(pastSessionProblem(at(9), at(10, 30), now), isNull);
    });

    test('a session that ends in the future is a timer, not a log', () {
      expect(pastSessionProblem(at(14), at(15, 30), now), contains('future'));
    });

    test('more than 16 hours is refused', () {
      expect(pastSessionProblem(DateTime(2026, 10, 13, 7), at(0), now), contains('16 hours'));
    });

    test('touching another session is fine; overlapping it is not', () {
      final spans = [DaySpan(at(9, 41), at(11, 5), 'Northwind')];
      expect(pastSessionProblem(at(8), at(9, 41), now, existing: spans), isNull);
      expect(pastSessionProblem(at(11, 5), at(12), now, existing: spans), isNull);
      expect(pastSessionProblem(at(11), at(12), now, existing: spans), 'That overlaps 9:41–11:05 on Northwind.');
    });

    test('the running session counts up to now', () {
      final running = [DaySpan(at(13), null, 'Studio Kite')];
      expect(pastSessionProblem(at(14), at(14, 30), now, existing: running), 'That overlaps 13:00–now on Studio Kite.');
      expect(pastSessionProblem(at(12), at(13), now, existing: running), isNull);
    });
  });

  group('sessionTimes', () {
    test('an end before the start runs past midnight', () {
      final (start, end) = sessionTimes(DateTime(2026, 10, 13), (23, 30), (0, 45));
      expect(start, DateTime(2026, 10, 13, 23, 30));
      expect(end, DateTime(2026, 10, 14, 0, 45));
    });

    test('an ordinary range stays on its day', () {
      final (start, end) = sessionTimes(DateTime(2026, 10, 14), (9, 0), (10, 30));
      expect(end.difference(start), const Duration(minutes: 90));
    });
  });
}
