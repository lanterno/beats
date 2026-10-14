import 'package:beats_companion/services/body_story.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> day(String date, Map<String, Object?> fields, {String source = 'oura'}) =>
    {'date': date, 'source': source, ...fields};

void main() {
  group('recoveryLine', () {
    test('above the HRV average and down two beats', () {
      final week = BodyWeek([
        day('2026-10-12', {'hrv_ms': 40, 'resting_hr_bpm': 59}),
        day('2026-10-13', {'hrv_ms': 41, 'resting_hr_bpm': 59}),
        day('2026-10-14', {'hrv_ms': 49, 'resting_hr_bpm': 56}),
      ]);
      expect(recoveryLine(week), 'HRV is above your seven-day average and resting heart rate is down two beats.');
    });

    test('within 5% of the average reads as close to, and one beat is singular', () {
      final week = BodyWeek([
        day('2026-10-13', {'hrv_ms': 44, 'resting_hr_bpm': 57}),
        day('2026-10-14', {'hrv_ms': 45, 'resting_hr_bpm': 58}),
      ]);
      // HRV 45 vs avg 44.5; RHR 58 vs 57.5 rounds to +1 (round half away from zero).
      expect(recoveryLine(week), 'HRV is close to your seven-day average and resting heart rate is up one beat.');
    });

    test('a level resting rate, HRV below', () {
      final week = BodyWeek([
        day('2026-10-13', {'hrv_ms': 50, 'resting_hr_bpm': 56}),
        day('2026-10-14', {'hrv_ms': 40, 'resting_hr_bpm': 56}),
      ]);
      expect(recoveryLine(week), 'HRV is below your seven-day average and resting heart rate is level.');
    });

    test('one measure alone still makes a sentence; neither is null', () {
      expect(
        recoveryLine(BodyWeek([day('2026-10-14', {'resting_hr_bpm': 60})])),
        'Resting heart rate is level.',
      );
      expect(recoveryLine(BodyWeek([day('2026-10-14', {'steps': 100})])), isNull);
    });

    test('ten beats or more are written as digits', () {
      final week = BodyWeek([
        for (final d in ['10', '11', '12', '13', '14', '15']) day('2026-10-$d', {'resting_hr_bpm': 70}),
        day('2026-10-16', {'resting_hr_bpm': 56}),
      ]);
      expect(recoveryLine(week), 'Resting heart rate is down 12 beats.');
    });
  });

  group('metricNote', () {
    test('sleep leads with the newest efficiency, as a fraction or a percentage', () {
      final week = BodyWeek([
        day('2026-10-13', {'sleep_minutes': 400}),
        day('2026-10-14', {'sleep_minutes': 432, 'sleep_efficiency': 0.914}),
      ]);
      expect(metricNote(week, 'sleep_minutes'), '91% efficient · week avg 6h 56m');
      expect(
        metricNote(BodyWeek([day('2026-10-14', {'sleep_minutes': 420, 'sleep_efficiency': 88})]), 'sleep_minutes'),
        '88% efficient · week avg 7h 00m',
      );
    });

    test('sleep without efficiency, and the other measures, give the average', () {
      final week = BodyWeek([
        day('2026-10-13', {'sleep_minutes': 400, 'hrv_ms': 42.4, 'resting_hr_bpm': 57, 'steps': 8200}),
        day('2026-10-14', {'sleep_minutes': 432, 'hrv_ms': 43.4, 'resting_hr_bpm': 58, 'steps': 6920}),
      ]);
      expect(metricNote(week, 'sleep_minutes'), 'Week avg 6h 56m');
      expect(metricNote(week, 'hrv_ms'), 'Week avg 43 ms');
      expect(metricNote(week, 'resting_hr_bpm'), 'Week avg 58 bpm');
      expect(metricNote(week, 'steps'), 'Week avg 7,560');
    });

    test('a measure with no data this week has no note', () {
      expect(metricNote(BodyWeek([day('2026-10-14', {'steps': 1})]), 'hrv_ms'), isNull);
    });
  });

  test('formatSteps groups thousands', () {
    expect(formatSteps(0), '0');
    expect(formatSteps(999), '999');
    expect(formatSteps(1840), '1,840');
    expect(formatSteps(1234567.4), '1,234,567');
  });

  group('BodyWeek.on and lastSynced', () {
    final week = BodyWeek([
      day('2026-10-14', {'sleep_minutes': 400, 'created_at': '2026-10-14T05:02:00Z'}, source: 'fitbit'),
      day('2026-10-14', {'sleep_minutes': 444, 'created_at': '2026-10-14T07:02:00Z'}),
      day('2026-10-13', {'hrv_ms': 41, 'created_at': 'not a time'}),
    ]);

    test('the later entry for a date wins', () {
      expect(week.on('2026-10-14', 'sleep_minutes'), 444);
      expect(week.on('2026-10-13', 'sleep_minutes'), isNull);
    });

    test('the newest created_at, skipping ones that do not parse', () {
      expect(week.lastSynced, DateTime.utc(2026, 10, 14, 7, 2));
      expect(const BodyWeek([]).lastSynced, isNull);
    });
  });

  group('sleep and flow', () {
    final days = [for (var d = 8; d <= 14; d++) DateTime(2026, 10, d)];

    test('pairs each day with the sleep that ended on it and that day\'s flow', () {
      final week = BodyWeek([
        day('2026-10-08', {'sleep_minutes': 450}),
        day('2026-10-10', {'sleep_minutes': 354}),
      ]);
      final pairs = pairSleepWithFlow(week, {'2026-10-08': 79, '2026-10-09': 61}, days);
      expect(pairs.length, 7);
      expect(pairs[0].sleepHours, 7.5);
      expect(pairs[0].flow, 79);
      expect(pairs[1].sleepHours, isNull);
      expect(pairs[1].flow, 61);
      expect(pairs[2].sleepHours, closeTo(5.9, 1e-9));
      expect(pairs[2].flow, isNull);
    });

    test('compares long nights with short ones, rounding the averages', () {
      final pairs = [
        SleepFlowPair(days[0], 7.5, 79),
        SleepFlowPair(days[1], 7.0, 64), // exactly seven counts as long
        SleepFlowPair(days[2], 5.9, 55),
        SleepFlowPair(days[3], 5.0, 62),
        SleepFlowPair(days[4], 6.5, 99), // between six and seven: neither
        SleepFlowPair(days[5], 8.0, null), // no flow after it: not counted
      ];
      expect(sleepFlowLine(pairs), 'After nights over seven hours your flow averaged 72. Under six, it was 59.');
    });

    test('says nothing when either group has no tracked day after it', () {
      expect(sleepFlowLine([SleepFlowPair(days[0], 7.5, 79), SleepFlowPair(days[1], 5.5, null)]), isNull);
      expect(sleepFlowLine([SleepFlowPair(days[0], 5.5, 50)]), isNull);
      expect(sleepFlowLine(const []), isNull);
    });
  });
}
