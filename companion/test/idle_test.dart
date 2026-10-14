// Time away: the tracker reads stretches out of idle readings, and the
// watcher only asks about a stretch the running session covered, and only
// cuts it out while that session is still the one running.

import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/services/idle_tracker.dart';
import 'package:beats_companion/state/idle_watcher.dart';
import 'package:beats_companion/state/prefs.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

DateTime at(int h, [int m = 0]) => DateTime(2026, 10, 14, h, m);

class _Api extends ApiClient {
  _Api() : super(baseUrl: 'http://test');
  final calls = <String>[];
  Map<String, dynamic> status = {'isBeating': false};
  final project = {'id': 'p1', 'name': 'Northwind', 'color': '#4F8FD6', 'kind': 'day_job'};

  @override
  Future<Map<String, dynamic>> getTimerStatus() async => status;
  @override
  Future<List<Map<String, dynamic>>> getProjects() async => [project];
  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime}) async {
    calls.add('stop $stopTime');
    status = {'isBeating': false};
    return {'id': 'b1', 'project_id': 'p1', 'start': '', 'end': stopTime};
  }

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime}) async {
    calls.add('start $startTime');
    status = {'isBeating': true, 'project': project, 'since': startTime};
    return {};
  }
}

void main() {
  group('IdleTracker', () {
    test('a stretch starts at the last input and ends when input comes back', () {
      final t = IdleTracker();
      expect(t.sample(at(12, 15), const Duration(minutes: 9)), isNull);
      expect(t.sample(at(12, 20), const Duration(minutes: 14)), isNull); // away since 12:06
      expect(t.sample(at(12, 40), const Duration(minutes: 34)), isNull);
      final p = t.sample(at(12, 41), const Duration(seconds: 10))!;
      expect(p.from, at(12, 6));
      expect(p.to, at(12, 41).subtract(const Duration(seconds: 10)));
    });

    test('nine minutes without input is not away', () {
      final t = IdleTracker();
      t.sample(at(12, 9), const Duration(minutes: 9));
      expect(t.sample(at(12, 10), Duration.zero), isNull);
    });

    test('a reading between "away" and "back" waits for clearer input', () {
      final t = IdleTracker();
      t.sample(at(12, 20), const Duration(minutes: 15));
      expect(t.sample(at(12, 22), const Duration(minutes: 3)), isNull);
      expect(t.away, isTrue);
    });
  });

  group('IdleWatcher', () {
    late _Api api;
    late TimerController timer;
    var idle = Duration.zero;
    final asked = <AwayAsk>[];

    setUp(() async {
      SharedPreferences.setMockInitialValues({Prefs.askOnIdle: true});
      api = _Api();
      timer = TimerController(api);
      await timer.refresh();
      await timer.startProject(timer.projectById('p1')!, at: at(9).toUtc());
      asked.clear();
    });
    tearDown(() => timer.dispose());

    IdleWatcher watcher() => IdleWatcher(timer, readIdle: () async => idle, notify: (a) async => asked.add(a));

    test('asks once input comes back, and taking it off cuts the stretch out', () async {
      final w = watcher();
      idle = const Duration(minutes: 20);
      await w.check(now: at(12, 20));
      idle = Duration.zero;
      await w.check(now: at(12, 45));
      expect(asked.single.period.from, at(12));
      expect(w.pending, isNotNull);

      api.calls.clear();
      await w.takeOff();
      expect(api.calls, ['stop ${at(12).toUtc().toIso8601String()}', 'start ${at(12, 45).toUtc().toIso8601String()}']);
      expect(w.pending, isNull);
    });

    test('does nothing to a timer that was stopped or switched since', () async {
      final w = watcher();
      idle = const Duration(minutes: 20);
      await w.check(now: at(12, 20));
      idle = Duration.zero;
      await w.check(now: at(12, 45));
      await timer.switchTo(timer.projectById('p1')!, at: at(12, 50).toUtc());

      api.calls.clear();
      await w.takeOff();
      expect(api.calls, isEmpty);
    });

    test('stays quiet with the setting off', () async {
      SharedPreferences.setMockInitialValues({});
      final w = watcher();
      idle = const Duration(minutes: 20);
      await w.check(now: at(12, 20));
      idle = Duration.zero;
      await w.check(now: at(12, 45));
      expect(asked, isEmpty);
    });
  });
}
