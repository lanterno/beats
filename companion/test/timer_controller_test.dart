// TimerController against a scripted API: the rules the redesign leans on
// are that a switch closes one session and opens the next at the same
// instant, and that undoing a stop reopens that session instead of
// starting a second one.

import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeApi extends ApiClient {
  FakeApi() : super(baseUrl: 'http://test');

  final calls = <String>[];
  Map<String, dynamic> status = {'isBeating': false};
  final projects = [
    {'id': 'p1', 'name': 'Northwind', 'color': '#4F8FD6', 'kind': 'day_job'},
    {'id': 'p2', 'name': 'Studio Kite', 'color': '#E07A5F', 'kind': 'freelance'},
  ];

  @override
  Future<Map<String, dynamic>> getTimerStatus() async => status;

  @override
  Future<List<Map<String, dynamic>>> getProjects() async => projects;

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime}) async {
    calls.add('start $projectId $startTime');
    status = {'isBeating': true, 'project': projects.firstWhere((p) => p['id'] == projectId), 'since': startTime};
    return {};
  }

  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime}) async {
    calls.add('stop $stopTime');
    final beat = {
      'id': 'b1',
      'project_id': (status['project'] as Map)['id'],
      'start': status['since'],
      'end': stopTime,
    };
    status = {'isBeating': false};
    return beat;
  }

  @override
  Future<Map<String, dynamic>> updateBeat({
    required String id,
    required String projectId,
    required DateTime start,
    DateTime? end,
  }) async {
    calls.add('update $id $projectId ${start.toIso8601String()} end=$end');
    status = {
      'isBeating': end == null,
      'project': projects.firstWhere((p) => p['id'] == projectId),
      'since': start.toIso8601String(),
    };
    return {};
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('switchTo stops and starts at the same instant', () async {
    final api = FakeApi();
    final timer = TimerController(api);
    await timer.refresh();
    final kite = timer.projectById('p2')!;
    await timer.startProject(timer.projectById('p1')!, at: DateTime.utc(2026, 10, 14, 9, 41));

    final at = DateTime.utc(2026, 10, 14, 11, 0);
    await timer.switchTo(kite, at: at);

    expect(api.calls.sublist(1), [
      'stop ${at.toIso8601String()}',
      'start p2 ${at.toIso8601String()}',
    ]);
    expect(timer.current?.id, 'p2');
    expect(timer.since, at);
    timer.dispose();
  });

  test('stop keeps the closed session and its length for undo', () async {
    final api = FakeApi();
    final timer = TimerController(api);
    await timer.refresh();
    await timer.startProject(timer.projectById('p1')!, at: DateTime.utc(2026, 10, 14, 9, 41));

    final stopped = await timer.stop(at: DateTime.utc(2026, 10, 14, 11, 5));

    expect(timer.running, isFalse);
    expect(stopped?.length, const Duration(hours: 1, minutes: 24));
    expect(timer.lastStopped?.project.name, 'Northwind');
    timer.dispose();
  });

  test('undoStop reopens the same session from its original start', () async {
    final api = FakeApi();
    final timer = TimerController(api);
    await timer.refresh();
    final start = DateTime.utc(2026, 10, 14, 9, 41);
    await timer.startProject(timer.projectById('p1')!, at: start);
    await timer.stop(at: DateTime.utc(2026, 10, 14, 11, 5));

    await timer.undoStop();

    expect(api.calls.last, 'update b1 p1 ${start.toIso8601String()} end=null');
    expect(api.calls.where((c) => c.startsWith('start')), hasLength(1));
    expect(timer.running, isTrue);
    expect(timer.since, start);
    expect(timer.lastStopped, isNull);
    timer.dispose();
  });

  test('a start puts the project first in recentFirst', () async {
    final api = FakeApi();
    final timer = TimerController(api);
    await timer.refresh();
    expect(timer.recentFirst.first.id, 'p1');

    await timer.startProject(timer.projectById('p2')!);

    expect(timer.recentFirst.map((p) => p.id), ['p2', 'p1']);
    timer.dispose();
  });
}
