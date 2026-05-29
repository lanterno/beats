import 'package:beats_companion/services/date_keys.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('dayKey', () {
    test('formats with zero-padding', () {
      expect(dayKey(DateTime(2026, 3, 9)), '2026-03-09');
      expect(dayKey(DateTime(2026, 12, 31)), '2026-12-31');
      expect(dayKey(DateTime(7, 1, 5)), '0007-01-05');
    });
  });

  group('addDays', () {
    test('steps forward and back', () {
      expect(dayKey(addDays(DateTime(2026, 3, 9), 1)), '2026-03-10');
      expect(dayKey(addDays(DateTime(2026, 3, 9), -1)), '2026-03-08');
    });

    test('rolls over month and year boundaries', () {
      expect(dayKey(addDays(DateTime(2026, 1, 31), 1)), '2026-02-01');
      expect(dayKey(addDays(DateTime(2026, 12, 31), 1)), '2027-01-01');
      expect(dayKey(addDays(DateTime(2026, 1, 1), -1)), '2025-12-31');
    });

    test('stepping across a spring-forward date stays on consecutive days', () {
      // US spring-forward is 2026-03-08. Component math lands on the right
      // calendar day regardless of the zone's DST; 24h Duration math would
      // skip/duplicate a day in a DST zone.
      var d = DateTime(2026, 3, 6);
      final keys = <String>[];
      for (var i = 0; i < 5; i++) {
        keys.add(dayKey(d));
        d = addDays(d, 1);
      }
      expect(keys, ['2026-03-06', '2026-03-07', '2026-03-08', '2026-03-09', '2026-03-10']);
    });

    test('returns local midnight of the target day', () {
      final d = addDays(DateTime(2026, 5, 29, 14, 30, 15), 1);
      expect([d.hour, d.minute, d.second], [0, 0, 0]);
      expect(dayKey(d), '2026-05-30');
    });
  });

  group('computeTimerStats', () {
    // 2026-05-27 is a Wednesday → week is Mon 05-25 .. Sun 05-31.
    final wed = DateTime(2026, 5, 27, 10);

    test('today minutes come from the today key', () {
      expect(computeTimerStats({'2026-05-27': 42}, wed).todayMinutes, 42);
    });

    test('week sums Mon..Sun of the week containing today', () {
      final stats = computeTimerStats({
        '2026-05-25': 10, // Mon (this week)
        '2026-05-27': 20, // Wed (this week)
        '2026-05-31': 5, // Sun (this week)
        '2026-05-24': 99, // previous Sun — excluded
      }, wed);
      expect(stats.weekMinutes, 35);
    });

    test('last week sums the prior Mon..Sun', () {
      final stats = computeTimerStats({
        '2026-05-18': 7, // last Mon
        '2026-05-24': 3, // last Sun
        '2026-05-25': 100, // this Mon — excluded from last week
      }, wed);
      expect(stats.lastWeekMinutes, 10);
    });

    test('streak walks back consecutively, forgiving a zero today', () {
      final stats = computeTimerStats({
        // 2026-05-27 (today) absent → 0, forgiven
        '2026-05-26': 30,
        '2026-05-25': 15,
        '2026-05-24': 5,
        // 2026-05-23 missing → streak stops at 3
        '2026-05-22': 99,
      }, wed);
      expect(stats.streakDays, 3);
    });

    test('streak counts today when today has minutes', () {
      final stats = computeTimerStats({'2026-05-27': 10, '2026-05-26': 10}, wed);
      expect(stats.streakDays, 2);
    });

    test('empty map yields all zeros', () {
      final stats = computeTimerStats({}, wed);
      expect(
        [stats.todayMinutes, stats.weekMinutes, stats.lastWeekMinutes, stats.streakDays],
        [0, 0, 0, 0],
      );
    });
  });
}
