// The offline client against a scripted server that keeps the API's rules
// for the four writes: one timer at a time; a stop or an edit refused when
// the session it names is no longer the stored one; a repeat of a write
// answered from the record of its X-Client-Id. The network can go down,
// and an answer can be lost after the server applied the write.

import 'dart:async';
import 'dart:io';

import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/services/local_store.dart';
import 'package:beats_companion/services/offline_api.dart';
import 'package:beats_companion/services/offline_queue.dart';
import 'package:beats_companion/services/offline_view.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 14 Oct 2026 at [hhmm] UTC.
String at(String hhmm) => '2026-10-14T$hhmm:00.000Z';
DateTime time(String hhmm) => DateTime.parse(at(hhmm));
String hm(Object? iso) => DateTime.parse(iso as String).toUtc().toIso8601String().substring(11, 16);

class Server extends ApiClient {
  Server() : super(baseUrl: 'http://test');

  /// No route to the server: requests fail before they leave.
  bool down = false;

  /// Writes are applied and their answers lost on the way back.
  bool loseAnswers = false;

  /// Answered to every write instead of applying it, until cleared.
  ApiException? failWith;

  /// The writes applied, in order, as "start p1 09:00".
  final applied = <String>[];

  /// The answer recorded under each X-Client-Id.
  final record = <String, Map<String, dynamic>>{};

  final beats = <Map<String, dynamic>>[];
  var _ids = 0;

  final projects = [
    {'id': 'p1', 'name': 'Northwind', 'color': '#4F8FD6', 'kind': 'day_job'},
    {'id': 'p2', 'name': 'Studio Kite', 'color': '#E07A5F', 'kind': 'freelance'},
    {'id': 'p3', 'name': 'Garden', 'color': '#6BAA75', 'kind': 'side_project'},
  ];

  Map<String, dynamic>? get running => beats.where((b) => b['end'] == null).firstOrNull;

  /// Another device, the web or the daemon writing directly.
  Map<String, dynamic> elsewhere(String project, String start, [String? end]) {
    final b = {'id': 'b${++_ids}', 'project_id': project, 'start': start, 'end': end};
    beats.add(b);
    return b;
  }

  Future<T> _reach<T>(T Function() answer) async {
    if (down) throw const SocketException('Failed host lookup: test');
    return answer();
  }

  Future<Map<String, dynamic>> _write(String? key, Map<String, dynamic> Function() apply) => _reach(() {
        final answer = key != null && record.containsKey(key)
            ? record[key]!
            : (failWith != null ? throw failWith! : apply());
        if (key != null) record[key] = answer;
        if (loseAnswers) throw TimeoutException('the answer was lost');
        return answer;
      });

  static bool _matches(Map<String, dynamic> beat, ExpectedBeat e) =>
      beat['project_id'] == e.projectId &&
      sameInstant(beat['start'], e.start) &&
      sameInstant(beat['end'], e.end);

  @override
  Future<Map<String, dynamic>> getTimerStatus() => _reach(() {
        final r = running;
        if (r == null) return {'isBeating': false};
        return {'isBeating': true, 'project': projects.firstWhere((p) => p['id'] == r['project_id']), 'since': r['start']};
      });

  @override
  Future<List<Map<String, dynamic>>> getProjects() => _reach(() => [for (final p in projects) Map.of(p)]);

  @override
  Future<List<Map<String, dynamic>>> getBeatsOn(DateTime utcDay) => _reach(() => [
        for (final b in beats)
          if (DateTime.parse(b['start'] as String).toUtc().day == utcDay.day) Map.of(b),
      ]);

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime, String? clientId}) =>
      _write(clientId, () {
        if (running != null) throw ApiException(400, 'Start timer failed: A timer is already running');
        applied.add('start $projectId ${hm(startTime)}');
        return Map.of(elsewhere(projectId, startTime!));
      });

  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime, ExpectedBeat? expected, String? clientId}) =>
      _write(clientId, () {
        final r = running;
        if (r == null) throw ApiException(400, 'Stop timer failed: No timer is currently running');
        if (expected != null && !_matches(r, expected)) {
          throw ApiException(409, 'Stop timer failed: A different timer is running now', code: 'TIMER_CHANGED');
        }
        r['end'] = stopTime;
        applied.add('stop ${r['project_id']} ${hm(stopTime)}');
        return Map.of(r);
      });

  @override
  Future<Map<String, dynamic>> createBeat({
    required String projectId,
    required DateTime start,
    required DateTime end,
    String? clientId,
  }) =>
      _write(clientId, () {
        applied.add('log $projectId ${hm(start.toIso8601String())}-${hm(end.toIso8601String())}');
        return Map.of(elsewhere(projectId, start.toIso8601String(), end.toIso8601String()));
      });

  @override
  Future<Map<String, dynamic>> updateBeat({
    required String id,
    required String projectId,
    required DateTime start,
    DateTime? end,
    ExpectedBeat? expected,
    String? clientId,
  }) =>
      _write(clientId, () {
        final b = beats.where((b) => b['id'] == id).firstOrNull;
        if (b == null) throw ApiException(404, 'Update beat failed: Beat not found', code: 'NOT_FOUND');
        if (expected != null && !_matches(b, expected)) {
          throw ApiException(409, 'Update beat failed: This session changed elsewhere', code: 'BEAT_CHANGED');
        }
        b
          ..['project_id'] = projectId
          ..['start'] = start.toIso8601String()
          ..['end'] = end?.toIso8601String();
        applied.add('edit $id ${hm(b['start'])}-${end == null ? 'running' : hm(b['end'])}');
        return Map.of(b);
      });
}

/// Lets every replay a read or a write set off run to its end.
Future<void> settle() async {
  for (var i = 0; i < 20; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  late Server server;
  late MemoryStore store;
  late OfflineApi api;

  /// The device has read the timer and the projects once, then lost the
  /// network.
  Future<void> offline() async {
    await api.getTimerStatus();
    await api.getProjects();
    server.down = true;
  }

  void fresh() {
    server = Server();
    store = MemoryStore();
    api = OfflineApi(server, store: Future.value(store));
  }

  setUp(fresh);

  test('offline, a start waits with its own key and the time it was pressed, and replays once a read gets through',
      () async {
    await offline();

    final placeholder = await api.startTimer('p1', startTime: at('09:00'));

    expect(placeholder['queued'], isA<int>());
    expect(api.status.online, isFalse);
    expect(api.status.pending, 1);
    final status = await api.getTimerStatus();
    expect((status['project'] as Map)['name'], 'Northwind');
    expect(hm(status['since']), '09:00');
    final key = (await store.queued()).single.clientId;

    server.down = false;
    await api.getTimerStatus();
    await settle();

    expect(server.applied, ['start p1 09:00']);
    expect(server.record.keys, [key]);
    expect(api.status.pending, 0);
    expect(api.status.online, isTrue);
  });

  test('a stop made offline lands at the time it was pressed, not the time it was replayed', () async {
    server.elsewhere('p1', at('09:00'));
    await offline();

    await api.stopTimer(stopTime: at('11:05'), expected: ExpectedBeat(projectId: 'p1', start: time('09:00')));
    server.down = false;
    await api.getTimerStatus();
    await settle();

    expect(hm(server.beats.single['end']), '11:05');
  });

  test('an answer lost on the way back is replayed under the same key and applied once', () async {
    await api.getTimerStatus();
    server.loseAnswers = true;

    await api.startTimer('p1', startTime: at('09:00'));

    expect(server.applied, ['start p1 09:00']);
    final write = (await store.queued()).single;
    expect(write.attempts, 1, reason: 'it may have landed, so it counts as sent');
    expect(await api.cancelQueued(write.id!), isFalse, reason: 'only the server knows whether it landed');

    server.loseAnswers = false;
    await api.drain();

    // Without the key the replay would be a second start, refused because
    // the first one runs.
    expect(server.applied, ['start p1 09:00']);
    expect(api.status.pending, 0);
    expect(api.status.refused, isEmpty);
  });

  test('a request that never left is queued as unsent, so it can still be taken back', () async {
    await api.getTimerStatus();
    server.down = true;

    final placeholder = await api.startTimer('p1', startTime: at('09:00'));

    expect((await store.queued()).single.attempts, 0);
    expect(await api.cancelQueued(placeholder['queued'] as int), isTrue);
    expect(api.status.pending, 0);
  });

  test('writes replay in the order they were made', () async {
    server.elsewhere('p1', at('09:00'));
    await offline();

    await api.stopTimer(stopTime: at('10:00'), expected: ExpectedBeat(projectId: 'p1', start: time('09:00')));
    await api.startTimer('p2', startTime: at('10:00'));
    await api.createBeat(projectId: 'p3', start: time('07:00'), end: time('08:00'));
    await api.stopTimer(stopTime: at('12:00'), expected: ExpectedBeat(projectId: 'p2', start: time('10:00')));

    server.down = false;
    await api.getProjects();
    await settle();

    expect(server.applied, ['stop p1 10:00', 'start p2 10:00', 'log p3 07:00-08:00', 'stop p2 12:00']);
  });

  test('while writes wait, a new one goes behind them even with the server answering', () async {
    await offline();
    await api.startTimer('p1', startTime: at('09:00'));
    server
      ..down = false
      ..failWith = ApiException(503, 'Start timer failed: Service unavailable');
    await api.getProjects();
    await settle();
    expect(api.status.online, isTrue);
    expect(api.status.pending, 1);

    await api.stopTimer(stopTime: at('10:00'), expected: ExpectedBeat(projectId: 'p1', start: time('09:00')));

    expect(server.applied, isEmpty, reason: 'sent straight away, the stop would have gone ahead of its start');
    server.failWith = null;
    await api.drain();
    expect(server.applied, ['start p1 09:00', 'stop p1 10:00']);
  });

  test('a timer started elsewhere while offline is left running; the writes it overtook are refused and kept to read',
      () async {
    server.elsewhere('p1', at('09:00'));
    await offline();
    await api.stopTimer(stopTime: at('10:00'), expected: ExpectedBeat(projectId: 'p1', start: time('09:00')));
    await api.startTimer('p2', startTime: at('10:00'));

    // Meanwhile, on the web: Northwind stopped at 9:30, Garden started.
    server.running!['end'] = at('09:30');
    server.elsewhere('p3', at('09:45'));
    server.down = false;
    await api.drain();

    expect(server.applied, isEmpty);
    expect(server.running!['project_id'], 'p3');
    expect(api.status.pending, 0);
    expect(api.status.refused.map((r) => (r.kind, r.status, r.code)), [
      (WriteKind.stop, 409, 'TIMER_CHANGED'),
      (WriteKind.start, 400, null),
    ]);
    expect(api.status.refused.first.detail, 'A different timer is running now');
  });

  test('a queued edit of a session deleted elsewhere is refused, not recreated', () async {
    final b = server.elsewhere('p1', at('09:00'), at('10:00'));
    await offline();
    await api.updateBeat(
      id: b['id'] as String,
      projectId: 'p1',
      start: time('08:30'),
      end: time('10:00'),
      expected: ExpectedBeat(projectId: 'p1', start: time('09:00'), end: time('10:00')),
    );

    server.beats.clear();
    server.down = false;
    await api.drain();

    expect(server.beats, isEmpty);
    expect(api.status.refused.single.status, 404);
  });

  test('a refusal moves on to the next write; a failure worth waiting out keeps the write and stops', () async {
    final keep = [
      ApiException(503, 'Start timer failed: Service unavailable'),
      ApiException(429, 'Start timer failed: Too many requests'),
      ApiException(401, 'Start timer failed: Not authenticated'),
      ApiException(409, 'Start timer failed: Still being processed', code: 'IDEMPOTENT_IN_PROGRESS'),
    ];
    for (final e in keep) {
      fresh();
      await offline();
      await api.startTimer('p1', startTime: at('09:00'));
      await api.createBeat(projectId: 'p3', start: time('07:00'), end: time('08:00'));
      server
        ..down = false
        ..failWith = e;

      await api.drain();

      expect(api.status.pending, 2, reason: '${e.statusCode} ${e.code}');
      expect(api.status.refused, isEmpty, reason: '${e.statusCode} ${e.code}');
    }

    // The network going again mid-replay keeps the write too.
    fresh();
    await offline();
    await api.startTimer('p1', startTime: at('09:00'));
    await api.drain();
    expect(api.status.pending, 1);
    expect(api.status.online, isFalse);

    // Any other 4xx is final: replayed, it would be refused forever.
    server
      ..down = false
      ..failWith = ApiException(422, 'Start timer failed: Invalid time');
    await api.createBeat(projectId: 'p3', start: time('07:00'), end: time('08:00'));
    await api.drain();
    expect(api.status.pending, 0);
    expect(api.status.refused.map((r) => r.status), [422, 422]);
  });

  test('a write the other engine has begun sending can no longer be cancelled or retimed here', () async {
    await offline();
    final start = await api.startTimer('p1', startTime: at('09:00'));
    final id = start['queued'] as int;

    expect(await api.retimeQueued(id, time('08:30')), isTrue);
    expect(hm((await store.queued()).single.body['time']), '08:30');

    await store.markSent(id); // the window claims it for a replay
    expect(await api.retimeQueued(id, time('08:00')), isFalse);
    expect(await api.cancelQueued(id), isFalse);
    expect(api.status.pending, 1);
  });

  test('reopening a finished session, or a stop or edit that names no session, is never queued', () async {
    final b = server.elsewhere('p1', at('09:00'), at('10:00'));
    await offline();

    await expectLater(
      api.updateBeat(
        id: b['id'] as String,
        projectId: 'p1',
        start: time('09:00'),
        expected: ExpectedBeat(projectId: 'p1', start: time('09:00'), end: time('10:00')),
      ),
      throwsA(isA<NotWhileOffline>()),
    );
    await expectLater(api.stopTimer(stopTime: at('11:00')), throwsA(isA<NotWhileOffline>()));
    await expectLater(
      api.updateBeat(id: b['id'] as String, projectId: 'p1', start: time('08:30'), end: time('10:00')),
      throwsA(isA<NotWhileOffline>()),
    );
    expect(await store.queued(), isEmpty);
  });

  test('offline, the day reads as last seen with the sessions made since', () async {
    server.elsewhere('p1', at('09:00'), at('10:00'));
    await api.getBeatsOn(DateTime.utc(2026, 10, 14));
    await offline();

    await api.createBeat(projectId: 'p3', start: time('07:00'), end: time('08:00'));
    final day = await api.getBeatsOn(DateTime.utc(2026, 10, 14));

    expect(day.map((b) => (b['project_id'], hm(b['start']))), [('p1', '09:00'), ('p3', '07:00')]);
    expect((await api.getProjects()).map((p) => p['name']), ['Northwind', 'Studio Kite', 'Garden']);
  });

  test('the menu bar popover queues into the shared store and leaves the replay to the window', () async {
    final popover = OfflineApi(server, store: Future.value(store), drains: false);
    await popover.getTimerStatus();
    server.down = true;
    await popover.startTimer('p1', startTime: at('09:00'));

    server.down = false;
    await popover.getTimerStatus();
    await popover.drain();
    await settle();
    expect(server.applied, isEmpty);

    await api.drain();
    expect(server.applied, ['start p1 09:00']);

    // The popover's count follows on its next answer.
    expect(popover.status.pending, 1);
    await popover.getTimerStatus();
    await settle();
    expect(popover.status.pending, 0);
  });

  group('the timer over it', () {
    late TimerController timer;
    final today = DateTime.utc(2026, 10, 14);

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      timer = TimerController(api);
    });
    tearDown(() => timer.dispose());

    /// The window has shown the timer and today's sessions, then lost the
    /// network.
    Future<void> offline() async {
      await timer.refresh();
      await api.getBeatsOn(today);
      server.down = true;
    }

    test('undoing a stop that has not synced takes it back from the queue', () async {
      server.elsewhere('p1', at('09:00'));
      await offline();
      await timer.stop(at: time('11:00'));
      expect(timer.running, isFalse);

      await timer.undoStop();

      expect(timer.current?.id, 'p1');
      expect(timer.since, time('09:00'));
      expect(await store.queued(), isEmpty);
      server.down = false;
      await api.drain();
      expect(server.applied, isEmpty);
    });

    test('undoing a stop that may already have reached the server says so, and the stop syncs', () async {
      server.elsewhere('p1', at('09:00'));
      await timer.refresh();
      server.loseAnswers = true;
      await timer.stop(at: time('11:00'));

      await expectLater(timer.undoStop(), throwsA(isA<NotWhileOffline>()));

      server.loseAnswers = false;
      await api.drain();
      expect(server.applied, ['stop p1 11:00']);
      expect(server.running, isNull);
    });

    test('moving the start of a timer that has not synced rewrites the queued start', () async {
      await offline();
      await timer.startProject(timer.projectById('p1')!, at: time('09:00'));

      await timer.moveStart(time('08:30'));

      expect(timer.since, time('08:30'));
      expect(api.status.pending, 1);
      server.down = false;
      await api.drain();
      expect(server.applied, ['start p1 08:30']);
    });

    test('moving the start of a synced timer offline queues an edit, and a stop after it names the moved start',
        () async {
      final b = server.elsewhere('p1', at('09:00'));
      await offline();

      await timer.moveStart(time('08:30'));
      expect(timer.since, time('08:30'));
      await timer.stop(at: time('11:00'));

      server.down = false;
      await api.drain();
      expect(server.applied, ['edit ${b['id']} 08:30-running', 'stop p1 11:00']);
    });

    test('a start refused on replay gives way to the timer started elsewhere', () async {
      await offline();
      await timer.startProject(timer.projectById('p1')!, at: time('09:00'));
      expect(timer.current?.id, 'p1');

      server.elsewhere('p2', at('09:30'));
      server.down = false;
      await api.drain();
      await settle();

      expect(timer.current?.id, 'p2');
      expect(timer.sync?.refused.single.kind, WriteKind.start);
    });
  });
}
