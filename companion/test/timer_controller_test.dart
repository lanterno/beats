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
    {'id': 'p3', 'name': 'Old Harbour', 'color': '#888888', 'kind': 'side_project', 'archived': true},
  ];

  /// The running session's note as the server holds it, and each edit
  /// that wrote one.
  String? runningNote;
  final noteWrites = <String>[];

  @override
  Future<List<Map<String, dynamic>>> getBeatsOn(DateTime utcDay) async => [
        if (status['isBeating'] == true)
          {
            'id': 'running',
            'project_id': (status['project'] as Map)['id'],
            'start': status['since'],
            'end': null,
            'note': runningNote,
          },
      ];

  @override
  Future<Map<String, dynamic>> getTimerStatus() async => status;

  @override
  Future<List<Map<String, dynamic>>> getProjects() async => projects;

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime, String? clientId}) async {
    calls.add('start $projectId $startTime');
    status = {'isBeating': true, 'project': projects.firstWhere((p) => p['id'] == projectId), 'since': startTime};
    return {};
  }

  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime, ExpectedBeat? expected, String? clientId}) async {
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
    ExpectedBeat? expected,
    String? note,
    String? clientId,
  }) async {
    calls.add('update $id $projectId ${start.toIso8601String()} end=$end');
    if (note != null) {
      runningNote = note;
      noteWrites.add('$id expected=${expected?.projectId}@${expected?.start.toIso8601String()} note=$note');
    }
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

  group('the last project', () {
    test("is the project of the API's last session when nothing runs, whichever device tracked it", () async {
      final api = FakeApi()
        ..status = {
          'isBeating': false,
          'last_beat': {'id': 'b9', 'project_id': 'p2', 'end': '2026-10-14T10:00:00Z'},
        };
      final timer = TimerController(api);
      await timer.refresh();

      expect(timer.lastProject?.name, 'Studio Kite');
      timer.dispose();
    });

    test('is none for an archived project, or an account with no session yet', () async {
      final api = FakeApi()
        ..status = {
          'isBeating': false,
          'last_beat': {'id': 'b9', 'project_id': 'p3', 'end': '2026-10-14T10:00:00Z'},
        };
      final timer = TimerController(api);
      await timer.refresh();
      expect(timer.lastProject, isNull);

      api.status = {'isBeating': false};
      await timer.refresh();
      expect(timer.lastProject, isNull);
      timer.dispose();
    });

    test('is the running one while a timer runs', () async {
      final api = FakeApi();
      final timer = TimerController(api);
      await timer.refresh();
      await timer.startProject(timer.projectById('p1')!, at: DateTime.utc(2026, 10, 14, 9, 41));

      expect(timer.lastProject?.id, 'p1');
      timer.dispose();
    });
  });

  group('adding to the note', () {
    final start = DateTime.utc(2026, 10, 14, 9, 41);

    Future<(FakeApi, TimerController)> running({String? note}) async {
      final api = FakeApi()..runningNote = note;
      final timer = TimerController(api);
      await timer.refresh();
      await timer.startProject(timer.projectById('p1')!, at: start);
      return (api, timer);
    }

    test('writes the line after what the note holds, naming the running session', () async {
      final (api, timer) = await running(note: 'Sprint review');

      await timer.addToNote('called Ana');

      expect(api.noteWrites, ['running expected=p1@${start.toIso8601String()} note=Sprint review; called Ana']);
      expect(api.calls.last, 'update running p1 ${start.toIso8601String()} end=null');
      timer.dispose();
    });

    test('is refused when nothing runs, or when the note would pass its limit', () async {
      final api = FakeApi();
      final idle = TimerController(api);
      await idle.refresh();
      await expectLater(idle.addToNote('x'), throwsA(isA<NoteRefused>()));
      idle.dispose();

      final (full, timer) = await running(note: 'a' * noteLimit);
      await expectLater(timer.addToNote('one more'), throwsA(isA<NoteRefused>()));
      expect(full.noteWrites, isEmpty);
      timer.dispose();
    });
  });

  group('appendToNote', () {
    test('a first line is the note', () {
      expect(appendToNote(null, 'called Ana'), 'called Ana');
      expect(appendToNote('  ', ' called Ana '), 'called Ana');
    });

    test('stays on the one line a note is', () {
      expect(appendToNote('Sprint review', 'called Ana'), 'Sprint review; called Ana');
      expect(appendToNote('Sprint review.', 'Called Ana'), 'Sprint review. Called Ana');
      expect(appendToNote('Sprint review', 'called\nAna'), 'Sprint review; called Ana');
    });

    test('an empty line leaves the note as it was', () {
      expect(appendToNote('Sprint review', '   '), 'Sprint review');
    });
  });
}
