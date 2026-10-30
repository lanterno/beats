import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'local_store.dart';
import 'offline_queue.dart';
import 'offline_view.dart';
import 'sqlite_store.dart';

/// Whether this device can reach the API, and what is waiting to sync.
class SyncStatus extends ChangeNotifier {
  /// False after a request failed for want of a network, until one gets
  /// through. A server that answers with an error is reachable.
  bool online = true;
  bool syncing = false;
  int pending = 0;
  List<RefusedWrite> refused = const [];

  /// Counts the replays that changed what the API holds (a write applied
  /// or refused), so a listener knows when to read the timer afresh.
  int settled = 0;

  void _set({bool? online, bool? syncing, int? pending, List<RefusedWrite>? refused, bool settledOne = false}) {
    final before = (this.online, this.syncing, this.pending, this.refused.length, settled);
    this.online = online ?? this.online;
    this.syncing = syncing ?? this.syncing;
    this.pending = pending ?? this.pending;
    this.refused = refused ?? this.refused;
    if (settledOne) settled++;
    if (before != (this.online, this.syncing, this.pending, this.refused.length, settled)) notifyListeners();
  }
}

/// A write that can't wait for the network, thrown in place of queueing it.
class NotWhileOffline implements Exception {
  final String message;
  const NotWhileOffline(this.message);
  @override
  String toString() => message;
}

/// The API as this device has it (docs/companion-offline.md). Reads of the
/// timer, the projects, a day's sessions and a ledger go to [network] and
/// are kept; when the network fails the kept answer is served, with the
/// writes still waiting applied on top. Timer starts and stops, a session
/// logged after the fact and an edit go straight through when the queue is
/// empty and the API reachable, and otherwise wait in the queue, each with
/// its own idempotency key, to be replayed in order once a read gets
/// through. Everything else is the plain client's.
class OfflineApi extends ApiClient {
  final ApiClient network;
  final Future<LocalStore> _store;

  /// Whether this side replays the queue. The menu bar popover queues but
  /// leaves replaying to the window, so two engines never race the queue.
  final bool drains;
  final Duration timeout;
  final SyncStatus status = SyncStatus();
  Future<void>? _replay;

  OfflineApi(
    this.network, {
    Future<LocalStore>? store,
    this.drains = true,
    this.timeout = const Duration(seconds: 15),
  })  : _store = store ?? openLocalStore(),
        super(baseUrl: network.baseUrl, deviceToken: network.deviceToken) {
    unawaited(_publish());
  }

  // ---- Reads ----

  Future<Object?> _read(String key, Future<Object?> Function() fetch) async {
    final store = await _store;
    try {
      final fresh = await fetch().timeout(timeout);
      _reached();
      await store.write(key, jsonEncode(fresh));
      return fresh;
    } catch (e) {
      if (e is ApiException) {
        _reached();
        // A refusal is an answer; a failing server is not, and the kept
        // answer serves until it recovers.
        if (e.statusCode < 500) rethrow;
      } else {
        _unreachable();
      }
      final kept = await store.read(key);
      if (kept == null) rethrow;
      return jsonDecode(kept);
    }
  }

  List<Map<String, dynamic>> _maps(Object? list) => [for (final m in list as List) m as Map<String, dynamic>];

  @override
  Future<Map<String, dynamic>> getTimerStatus() async {
    final raw = await _read('timer', network.getTimerStatus) as Map<String, dynamic>;
    final store = await _store;
    final queue = await store.queued();
    if (queue.isEmpty) return raw;
    final kept = await store.read('projects');
    return statusWith(raw, queue, kept == null ? const [] : _maps(jsonDecode(kept)));
  }

  @override
  Future<List<Map<String, dynamic>>> getProjects() async => _maps(await _read('projects', network.getProjects));

  static String _dayKey(DateTime d) => 'beats:${d.toIso8601String().substring(0, 10)}';

  @override
  Future<List<Map<String, dynamic>>> getBeatsOn(DateTime utcDay) async {
    final day = DateTime.utc(utcDay.year, utcDay.month, utcDay.day);
    final fresh = _maps(await _read(_dayKey(day), () => network.getBeatsOn(day)));
    final store = await _store;
    await store.prune('beats:', _dayKey(day.subtract(const Duration(days: 14))));
    final queue = await store.queued();
    if (queue.isEmpty) return fresh;
    // A moved start can carry a session across UTC midnight, so the days
    // either side lend theirs before the result is filed by start day.
    final pool = [...fresh];
    for (final other in [day.subtract(const Duration(days: 1)), day.add(const Duration(days: 1))]) {
      final kept = await store.read(_dayKey(other));
      if (kept != null) pool.addAll(_maps(jsonDecode(kept)));
    }
    return [
      for (final b in beatsWith(pool, queue))
        if (_dayKey(DateTime.parse(b['start'] as String).toUtc()) == _dayKey(day)) b,
    ];
  }

  @override
  Future<Map<String, dynamic>> getLedger(String projectId, {int weeks = 1, String? timezone}) async =>
      await _read('ledger:$projectId:$weeks:${timezone ?? ''}',
          () => network.getLedger(projectId, weeks: weeks, timezone: timezone)) as Map<String, dynamic>;

  // ---- Writes ----

  String _now() => DateTime.now().toUtc().toIso8601String();

  QueuedWrite _new(WriteKind kind, Map<String, dynamic> body, String? clientId) =>
      QueuedWrite(kind: kind, body: body, clientId: clientId ?? newClientId(), enqueuedAt: DateTime.now().toUtc());

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime, String? clientId}) =>
      _write(_new(WriteKind.start, {'project_id': projectId, 'time': startTime ?? _now()}, clientId));

  /// Without [expected] a stop can't be replayed safely (it would stop
  /// whatever runs by then), so it is sent now or not at all.
  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime, ExpectedBeat? expected, String? clientId}) {
    final body = <String, dynamic>{'time': stopTime ?? _now(), 'expected': ?expected?.toJson()};
    return _write(_new(WriteKind.stop, body, clientId),
        unqueueable: expected == null ? 'Stopping needs a connection, and this device is offline.' : null);
  }

  @override
  Future<Map<String, dynamic>> createBeat({
    required String projectId,
    required DateTime start,
    required DateTime end,
    String? clientId,
  }) =>
      _write(_new(
        WriteKind.log,
        {'project_id': projectId, 'start': start.toUtc().toIso8601String(), 'end': end.toUtc().toIso8601String()},
        clientId,
      ));

  /// An edit waits in the queue only with [expected], and never when it
  /// sets a finished session running again: replayed later, that could
  /// start it beside a timer started elsewhere meanwhile.
  @override
  Future<Map<String, dynamic>> updateBeat({
    required String id,
    required String projectId,
    required DateTime start,
    DateTime? end,
    ExpectedBeat? expected,
    String? clientId,
  }) {
    final reopens = end == null && expected?.end != null;
    final body = <String, dynamic>{
      'id': id,
      'project_id': projectId,
      'start': start.toUtc().toIso8601String(),
      'end': end?.toUtc().toIso8601String(),
      'expected': ?expected?.toJson(),
    };
    return _write(
      _new(WriteKind.edit, body, clientId),
      unqueueable: reopens
          ? 'Undoing a stop needs a connection, and this device is offline.'
          : expected == null
              ? 'That change needs a connection, and this device is offline.'
              : null,
    );
  }

  Future<Map<String, dynamic>> _send(QueuedWrite w) {
    final b = w.body;
    DateTime at(String key) => DateTime.parse(b[key] as String);
    ExpectedBeat? expected() =>
        b['expected'] == null ? null : ExpectedBeat.fromJson(b['expected'] as Map<String, dynamic>);
    return switch (w.kind) {
      WriteKind.start =>
        network.startTimer(b['project_id'] as String, startTime: b['time'] as String, clientId: w.clientId),
      WriteKind.stop => network.stopTimer(stopTime: b['time'] as String, expected: expected(), clientId: w.clientId),
      WriteKind.log =>
        network.createBeat(projectId: b['project_id'] as String, start: at('start'), end: at('end'), clientId: w.clientId),
      WriteKind.edit => network.updateBeat(
          id: b['id'] as String,
          projectId: b['project_id'] as String,
          start: at('start'),
          end: b['end'] == null ? null : at('end'),
          expected: expected(),
          clientId: w.clientId,
        ),
    };
  }

  /// Sends [w] now when nothing waits ahead of it and the API was last
  /// reachable; otherwise, or when the network fails, queues it and returns
  /// the session it leaves behind ([QueuedWrite.placeholder]). An answer
  /// from the API, refusal or error, is thrown as ever: the person sees it.
  /// A write that mustn't wait says why in [unqueueable], thrown instead.
  Future<Map<String, dynamic>> _write(QueuedWrite w, {String? unqueueable}) async {
    final store = await _store;
    if (status.online && (await store.queued()).isEmpty) {
      try {
        final answer = await _send(w).timeout(timeout);
        _reached();
        return answer;
      } on ApiException {
        _reached();
        rethrow;
      } catch (e) {
        _unreachable();
        if (unqueueable != null) throw NotWhileOffline(unqueueable);
        // A request that may have landed keeps its key and counts as sent,
        // so it is never cancelled here behind the API's back.
        final id = await store.enqueue(w.copyWith(attempts: definitelyNotSent(e) ? 0 : 1, lastError: '$e'));
        await _publish();
        return w.placeholder(id);
      }
    }
    if (unqueueable != null) throw NotWhileOffline(unqueueable);
    final id = await store.enqueue(w);
    await _publish();
    if (status.online) unawaited(drain());
    return w.placeholder(id);
  }

  // ---- The queue ----

  /// Replays the queue in order, each write with its own key. A write the
  /// API applies leaves the queue; one it refuses for good moves to
  /// [SyncStatus.refused] and the next is tried; a network failure or an
  /// answer worth waiting out ([isRetryable]) stops the replay, keeping the
  /// write for the next one. While a replay runs, this is that replay.
  Future<void> drain() {
    if (!drains) return Future.value();
    return _replay ??= _replayQueue().whenComplete(() => _replay = null);
  }

  Future<void> _replayQueue() async {
    final store = await _store;
    var settled = false;
    try {
      while (true) {
        final head = (await store.queued()).firstOrNull;
        if (head == null) break;
        status._set(syncing: true);
        // Claimed as it stands now: a cancel or a rewrite from the other
        // engine either landed before this or can no longer happen.
        final next = await store.markSent(head.id!);
        if (next == null) continue;
        try {
          await _send(next).timeout(timeout);
          await store.remove(next.id!);
          settled = true;
          _reached();
        } on ApiException catch (e) {
          _reached();
          if (isRetryable(e)) {
            await store.note(next.id!, e.message);
            break;
          }
          await store.refuse(next.id!, RefusedWrite.from(next, e, DateTime.now().toUtc()));
          settled = true;
        } catch (e) {
          _unreachable();
          await store.note(next.id!, '$e');
          break;
        }
      }
    } finally {
      status._set(syncing: false);
      await _publish(settled: settled);
    }
  }

  /// Takes back a write never sent, as an undo of a stop made offline does.
  /// False once a request for it may have left: only the API knows then.
  Future<bool> cancelQueued(int id) async {
    final done = await (await _store).cancelUnsent(id);
    await _publish();
    return done;
  }

  /// Moves the time of a start never sent ("I started earlier", offline).
  Future<bool> retimeQueued(int id, DateTime at) async {
    final store = await _store;
    final write = (await store.queued()).where((w) => w.id == id && w.kind == WriteKind.start).firstOrNull;
    if (write == null) return false;
    final done = await store.rewriteUnsent(id, {...write.body, 'time': at.toUtc().toIso8601String()});
    await _publish();
    return done;
  }

  Future<void> dismissRefused() async {
    await (await _store).clearRefused();
    await _publish();
  }

  /// Forgets what this device kept for the pairing: on unpairing, and on a
  /// new pairing, which may be another account's.
  Future<void> forget() async {
    await (await _store).clear();
    await _publish();
  }

  void _reached() {
    status._set(online: true);
    if (!drains) {
      // The other engine replays; this one only follows how far it got.
      unawaited(_publish());
    } else if (_replay == null) {
      unawaited(_drainIfQueued());
    }
  }

  Future<void> _drainIfQueued() async {
    if ((await (await _store).queued()).isNotEmpty) await drain();
  }

  void _unreachable() => status._set(online: false);

  Future<void> _publish({bool settled = false}) async {
    final store = await _store;
    status._set(pending: (await store.queued()).length, refused: await store.refused(), settledOne: settled);
  }
}
