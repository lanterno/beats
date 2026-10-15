// Sample data read through the app's own controllers and parsers: a
// reviewer's first look depends on it agreeing with them, and on the real
// client's signatures it overrides.

import 'package:beats_companion/services/flow_story.dart';
import 'package:beats_companion/services/flow_summary.dart';
import 'package:beats_companion/services/sample_api.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:beats_companion/state/week_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  // A Wednesday afternoon.
  final now = DateTime(2026, 10, 14, 15, 30);
  DateTime clock() => now;

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('opens with Northwind running for 1h 24m', () async {
    final timer = TimerController(SampleApi(clock: clock));
    await timer.refresh();
    expect(timer.current?.name, 'Northwind');
    expect(now.toUtc().difference(timer.since!), const Duration(minutes: 84));
    expect(timer.projects, hasLength(4));
    timer.dispose();
  });

  test('stop, then undo, puts the same session back', () async {
    final api = SampleApi(clock: clock);
    final timer = TimerController(api);
    await timer.refresh();
    final since = timer.since;

    final stopped = await timer.stop();
    expect(stopped?.project.name, 'Northwind');
    expect(timer.running, isFalse);

    await timer.undoStop();
    await timer.refresh();
    expect(timer.current?.name, 'Northwind');
    expect(timer.since, since);
    timer.dispose();
  });

  test('a switch closes one session and opens the next', () async {
    final api = SampleApi(clock: clock);
    final timer = TimerController(api);
    await timer.refresh();
    await timer.switchTo(timer.projectById('kite')!);
    expect(timer.current?.name, 'Studio Kite');

    final today = await api.getBeatsOn(DateTime.utc(now.year, now.month, now.day));
    final northwind = today.where((b) => b['project_id'] == 'northwind').toList();
    expect(northwind.every((b) => b['end'] != null), isTrue);
    timer.dispose();
  });

  test('the week reads as a working week with today\'s sessions in it', () async {
    final api = SampleApi(clock: clock);
    final timer = TimerController(api);
    await timer.refresh();
    final week = WeekController(api, timer);
    await week.refresh();

    final anchor = week.anchor!;
    expect(anchor.project.name, 'Northwind');
    expect(anchor.target, 32);
    // Monday and Tuesday from history, Wednesday from the sessions.
    expect(anchor.days[0], greaterThan(5));
    expect(anchor.days[2], closeTo((75 + 84) / 60, 0.05));
    expect(anchor.days.sublist(3), everyElement(0));
    // About eight hours a day across the targets, not twelve.
    expect(week.dailyTargetMinutes(now), inInclusiveRange(7 * 60, 9 * 60));
    timer.dispose();
    week.dispose();
  });

  test('flow covers today\'s sessions and summarises as the headline expects', () async {
    final api = SampleApi(clock: clock);
    final day = DateTime(now.year, now.month, now.day);
    final from = day.toUtc().toIso8601String(), to = now.toUtc().toIso8601String();

    final samples = FlowSample.listFrom(await api.getFlowWindows(from, to));
    expect(samples, isNotEmpty);
    expect(samples.every((s) => s.score >= 0 && s.score <= 1), isTrue);
    expect(samples.last.start.isBefore(now), isTrue);

    final headline = parseFlowSummary(await api.getFlowWindowsSummary(from, to))!;
    expect(headline.avg, inInclusiveRange(40, 90));
    expect(headline.topRepo, 'northwind-api');
  });

  test('yesterday has a working day of flow too', () async {
    final api = SampleApi(clock: clock);
    final yesterday = DateTime(now.year, now.month, now.day - 1);
    final summary = parseFlowSummary(await api.getFlowWindowsSummary(
      yesterday.toUtc().toIso8601String(),
      DateTime(now.year, now.month, now.day).toUtc().toIso8601String(),
    ));
    expect(summary?.count, greaterThan(50));
  });

  test('a week of biometrics, one row a day, today last', () async {
    final api = SampleApi(clock: clock);
    final rows = await api.getBiometrics('2026-10-08', '2026-10-14');
    expect([for (final r in rows) r['date']], [
      '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11', '2026-10-12', '2026-10-13', '2026-10-14',
    ]);
    expect(rows.last['readiness_score'], 82);
  });

  test('pairing from sample data is refused, not attempted', () async {
    expect(SampleApi(clock: clock).exchangePairCode('ABC123'), throwsA(anything));
  });
}
