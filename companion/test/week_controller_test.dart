import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:beats_companion/state/week_controller.dart';
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';

const northwind = Project(id: 'p1', name: 'Northwind', color: Color(0xFF4F8FD6), kind: 'day_job');
const kite = Project(id: 'p2', name: 'Studio Kite', color: Color(0xFFE07A5F), kind: 'freelance');

Map<String, dynamic> ledger({
  double worked = 0,
  List<double>? days,
  double? expected,
  double? goal,
  String goalType = 'target',
  double? balance,
}) =>
    {
      'weeks': [
        {
          'week_of': '2026-10-12',
          'worked': worked,
          'days': days ?? List.filled(7, 0.0),
          'effective_goal': goal,
          'effective_goal_type': goalType,
          'effective_goal_overridden': false,
          'contract_expected': expected,
          'balance_end': null,
          'notes': [],
        },
      ],
      'since': null,
      'totals': balance == null ? null : {'expected': 0, 'worked': 0, 'balance': balance},
    };

void main() {
  group('ProjectWeek.fromLedger', () {
    test('a day job targets its contract expectation and carries its balance', () {
      final w = ProjectWeek.fromLedger(
        northwind,
        ledger(worked: 19.2, expected: 32, goal: 40, balance: 1.17),
      )!;
      expect(w.target, 32);
      expect(w.balance, 1.17);
      expect(w.worked, 19.2);
    });

    test('a target goal is a target; a cap is not', () {
      expect(ProjectWeek.fromLedger(kite, ledger(goal: 8))!.target, 8);
      expect(ProjectWeek.fromLedger(kite, ledger(goal: 8, goalType: 'cap'))!.target, isNull);
    });

    test('an empty ledger is no week, and a short days list reads as zeros', () {
      expect(ProjectWeek.fromLedger(kite, {'weeks': [], 'totals': null}), isNull);
      final w = ProjectWeek.fromLedger(kite, ledger(days: [1.0]))!;
      expect(w.days, List.filled(7, 0.0));
    });
  });

  group('WeekController', () {
    late TimerController timer;
    late WeekController week;
    final wednesday = DateTime(2026, 10, 14, 11, 5);

    setUp(() {
      final api = ApiClient(baseUrl: 'http://test');
      timer = TimerController(api);
      week = WeekController(api, timer);
      week.weeks = [
        ProjectWeek(project: northwind, worked: 17, days: [7.5, 8, 1.5, 0, 0, 0, 0], target: 40),
        ProjectWeek(project: kite, worked: 0.5, days: [0, 0, 0.5, 0, 0, 0, 0], target: 5),
      ];
    });

    tearDown(() => timer.dispose());

    test('today sums every project on today\'s weekday', () {
      expect(week.todayMinutes(wednesday), 120);
    });

    test('a running timer counts from the last reload, not twice', () {
      week.loadedAt = DateTime(2026, 10, 14, 10, 50);
      timer.current = northwind;
      timer.since = DateTime(2026, 10, 14, 9, 41).toUtc();
      // The ledger already counted 9:41–10:50; only 10:50–11:05 is new.
      expect(week.todayMinutes(wednesday), 135);
    });

    test('a timer started after the reload counts from its start', () {
      week.loadedAt = DateTime(2026, 10, 14, 10, 0);
      timer.current = kite;
      timer.since = DateTime(2026, 10, 14, 10, 45).toUtc();
      expect(week.todayMinutes(wednesday), 140);
    });

    test('the daily target spreads every target over the working week', () {
      expect(week.dailyTargetMinutes(wednesday), 540);
      expect(week.dailyTargetMinutes(DateTime(2026, 10, 17)), isNull);
    });

    test('the anchor is the day job', () {
      expect(week.anchor?.project.id, 'p1');
    });
  });

  group('WeekController.refresh', () {
    test('a slower, older reload does not overwrite a newer one', () async {
      final api = _SlowLedgerApi();
      final timer = TimerController(api)..projects = [northwind];
      final week = WeekController(api, timer);

      final first = week.refresh(); // its ledger answers last
      final second = week.refresh();
      await Future.wait([first, second]);

      expect(week.weeks.single.worked, 2, reason: 'the newer read wins');
      timer.dispose();
    });

    test('asks for a few ledgers at a time, not one per project at once',
        () async {
      // One per project at once is a burst the API answered with "no
      // available instance" (#376): this runs on every timer change, and a
      // ledger is its slowest read.
      final api = _CountingLedgerApi();
      final projects = [
        for (var i = 0; i < 9; i++)
          Project(id: 'p$i', name: 'P$i', color: const Color(0xFF4F8FD6), kind: 'side_project'),
      ];
      final timer = TimerController(api)..projects = projects;
      final week = WeekController(api, timer);

      await week.refresh();

      expect(api.peak, lessThanOrEqualTo(3), reason: 'no more than a few in flight');
      expect(api.calls, projects.length, reason: 'every project is still read');
      expect(week.weeks, hasLength(projects.length));
      timer.dispose();
    });

    test('is complete only once a reload has covered the projects', () async {
      final api = _SlowLedgerApi();
      final timer = TimerController(api);
      final week = WeekController(api, timer);

      await week.refresh(); // before the timer has read any projects
      expect(week.complete, isFalse);

      timer.projects = [northwind];
      await week.refresh();
      expect(week.complete, isTrue);
      timer.dispose();
    });
  });
}

/// Counts how many ledger reads are in flight at once.
class _CountingLedgerApi extends ApiClient {
  _CountingLedgerApi() : super(baseUrl: 'http://test');
  var calls = 0;
  var inFlight = 0;
  var peak = 0;

  @override
  Future<Map<String, dynamic>> getLedger(String projectId, {int weeks = 1, String? timezone}) async {
    calls++;
    inFlight++;
    if (inFlight > peak) peak = inFlight;
    await Future<void>.delayed(const Duration(milliseconds: 5));
    inFlight--;
    return ledger(worked: 1);
  }
}

class _SlowLedgerApi extends ApiClient {
  _SlowLedgerApi() : super(baseUrl: 'http://test');
  var calls = 0;

  @override
  Future<Map<String, dynamic>> getLedger(String projectId, {int weeks = 1, String? timezone}) async {
    final n = ++calls;
    if (n == 1) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
      return ledger(worked: 1);
    }
    return ledger(worked: 2);
  }
}
