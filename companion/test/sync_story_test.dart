import 'package:beats_companion/services/offline_queue.dart';
import 'package:beats_companion/services/sync_story.dart';
import 'package:beats_companion/services/time_format.dart';
import 'package:flutter_test/flutter_test.dart';

/// 14 Oct 2026 at [hhmm] UTC, and how the person reads it here.
String at(String hhmm) => '2026-10-14T$hhmm:00.000Z';
String shown(String hhmm) => formatTimeOfDay(DateTime.parse(at(hhmm)));

String nameOf(String? id) => const {'p1': 'Northwind', 'p2': 'Studio Kite'}[id] ?? 'a project';

RefusedWrite refused(WriteKind kind, Map<String, dynamic> body, int status, String detail, {String? code}) =>
    RefusedWrite(kind: kind, body: body, refusedAt: DateTime.utc(2026, 10, 14, 12), status: status, code: code, detail: detail);

void main() {
  group('describeSync', () {
    SyncLine line({bool online = true, bool syncing = false, int pending = 0, bool failing = false}) =>
        describeSync(online: online, syncing: syncing, pending: pending, failing: failing);

    test('says what waits before anything else, and only then whether the server answers', () {
      expect(line(syncing: true, pending: 2), (title: 'Syncing', detail: '2 changes on the way', tone: SyncTone.waiting));
      expect(line(online: false, pending: 1, failing: true),
          (title: 'Offline', detail: '1 change waiting to sync', tone: SyncTone.waiting));
      expect(line(online: false, failing: true), (title: 'Can\'t reach the server', detail: null, tone: SyncTone.trouble));
      expect(line(online: false), (title: 'Offline', detail: 'Changes will sync later', tone: SyncTone.waiting));
      expect(line(pending: 3), (title: '3 changes waiting to sync', detail: null, tone: SyncTone.waiting));
      expect(line(), (title: 'Synced', detail: null, tone: SyncTone.synced));
    });
  });

  group('describeRefusal', () {
    test('a stop overtaken by another device says the timer had changed', () {
      final r = refused(
        WriteKind.stop,
        {'time': at('10:30'), 'expected': {'project_id': 'p1', 'start': at('09:00'), 'end': null}},
        409,
        'A different timer is running now',
        code: 'TIMER_CHANGED',
      );

      expect(describeRefusal(r, nameOf),
          'Stopping Northwind at ${shown('10:30')} wasn\'t saved. The timer had changed on another device.');
    });

    test('an edit names the session as it was, and why it was left alone', () {
      final body = {
        'id': 'b1',
        'project_id': 'p2',
        'start': at('08:30'),
        'end': at('10:00'),
        'expected': {'project_id': 'p2', 'start': at('09:00'), 'end': at('10:00')},
      };
      final what = 'Changing the Studio Kite session from ${shown('09:00')} to ${shown('10:00')} wasn\'t saved.';

      expect(describeRefusal(refused(WriteKind.edit, body, 409, 'changed', code: 'BEAT_CHANGED'), nameOf),
          '$what That session had changed elsewhere.');
      expect(describeRefusal(refused(WriteKind.edit, body, 404, 'Beat not found', code: 'NOT_FOUND'), nameOf),
          '$what That session was deleted elsewhere.');
    });

    test('a moved start, a start and a logged session each say what they were', () {
      final moved = refused(
        WriteKind.edit,
        {'id': 'b1', 'project_id': 'p1', 'start': at('08:30'), 'end': null, 'expected': {}},
        409,
        'changed',
        code: 'BEAT_CHANGED',
      );
      expect(describeRefusal(moved, nameOf), startsWith('Moving the start of Northwind to ${shown('08:30')} wasn\'t'));

      final start = refused(WriteKind.start, {'project_id': 'p2', 'time': at('09:00')}, 400, 'A timer is already running');
      expect(describeRefusal(start, nameOf),
          'Starting Studio Kite at ${shown('09:00')} wasn\'t saved. A timer is already running.');

      final log = refused(WriteKind.log, {'project_id': 'gone', 'start': at('07:00'), 'end': at('08:00')}, 422, '');
      expect(describeRefusal(log, nameOf),
          'Logging a project from ${shown('07:00')} to ${shown('08:00')} wasn\'t saved. The server turned it down.');
    });

    test('the server\'s own words are made a sentence', () {
      final start = refused(WriteKind.start, {'project_id': 'p1', 'time': at('09:00')}, 400, 'project is archived.');

      expect(describeRefusal(start, nameOf), endsWith('wasn\'t saved. Project is archived.'));
    });
  });

  test('unpairing warns only while changes wait, and says how many', () {
    expect(unpairWarning(0), isNull);
    expect(unpairWarning(1), '1 change made offline hasn\'t reached the server yet. Unpairing now drops it.');
    expect(unpairWarning(3), '3 changes made offline haven\'t reached the server yet. Unpairing now drops them.');
  });
}
