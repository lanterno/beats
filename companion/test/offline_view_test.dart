// The timer and the sessions as the device shows them offline: the last
// answer with the queue applied on top. The view has to agree with what
// the API will do when the queue replays, and applying a write the answer
// already holds must change nothing, since a write can land before it
// leaves the queue.

import 'package:beats_companion/services/offline_queue.dart';
import 'package:beats_companion/services/offline_view.dart';
import 'package:flutter_test/flutter_test.dart';

const projects = [
  {'id': 'p1', 'name': 'Northwind', 'color': '#4F8FD6'},
  {'id': 'p2', 'name': 'Studio Kite', 'color': '#E07A5F'},
];

/// 14 Oct 2026 at [hhmm] UTC, as the device writes an instant.
String at(String hhmm) => '2026-10-14T$hhmm:00.000Z';

var _rows = 0;
QueuedWrite write(WriteKind kind, Map<String, dynamic> body) =>
    QueuedWrite(id: ++_rows, kind: kind, body: body, clientId: 'key-$_rows', enqueuedAt: DateTime.utc(2026, 10, 14));

QueuedWrite start(String project, String time) => write(WriteKind.start, {'project_id': project, 'time': time});

QueuedWrite stop(String time, {required String project, required String since}) => write(WriteKind.stop, {
      'time': time,
      'expected': {'project_id': project, 'start': since, 'end': null},
    });

Map<String, dynamic> running(String project, String since) =>
    {'isBeating': true, 'project': projects.firstWhere((p) => p['id'] == project), 'since': since};

void main() {
  group('statusWith', () {
    test('a start made offline runs the timer from the time it was pressed', () {
      final status = statusWith({'isBeating': false}, [start('p1', at('09:00'))], projects);

      expect(status['isBeating'], isTrue);
      expect((status['project'] as Map)['name'], 'Northwind');
      expect(status['since'], at('09:00'));
    });

    test('a start is not shown over a timer already running, which the API would refuse', () {
      final elsewhere = running('p2', at('08:00'));

      expect(statusWith(elsewhere, [start('p1', at('09:00'))], projects), same(elsewhere));
    });

    test('a stop ends only the timer it was made against', () {
      final mine = running('p1', at('09:00'));
      final queue = [stop(at('11:00'), project: 'p1', since: at('09:00'))];

      expect(statusWith(mine, queue, projects), {'isBeating': false});

      // Another device switched to Studio Kite meanwhile: the stop leaves it.
      final switched = running('p2', at('10:00'));
      expect(statusWith(switched, queue, projects), same(switched));
    });

    test('a switch made offline leaves the new project running from the switch', () {
      final queue = [
        stop(at('11:00'), project: 'p1', since: at('09:00')),
        start('p2', at('11:00')),
      ];

      final status = statusWith(running('p1', at('09:00')), queue, projects);

      expect((status['project'] as Map)['id'], 'p2');
      expect(status['since'], at('11:00'));
    });

    test('once the API holds the writes, applying them again changes nothing', () {
      // The switch above has landed: the answer already shows Studio Kite.
      final landed = running('p2', at('11:00'));
      final queue = [
        stop(at('11:00'), project: 'p1', since: at('09:00')),
        start('p2', at('11:00')),
      ];

      expect(statusWith(landed, queue, projects), same(landed));
    });

    test('instants match to the millisecond, the precision the API stores', () {
      // The device wrote microseconds; the API kept milliseconds and answers
      // with an offset instead of Z. Still the same session.
      final stored = running('p1', '2026-10-14T09:00:00.123000+00:00');

      final matching = stop(at('11:00'), project: 'p1', since: '2026-10-14T09:00:00.123456Z');
      expect(statusWith(stored, [matching], projects), {'isBeating': false});

      final another = stop(at('11:00'), project: 'p1', since: '2026-10-14T09:00:00.124Z');
      expect(statusWith(stored, [another], projects), same(stored));
    });

    test('a moved start, then a stop against the moved time, chain in order', () {
      final queue = [
        write(WriteKind.edit, {
          'id': 'b1',
          'project_id': 'p1',
          'start': at('08:30'),
          'end': null,
          'expected': {'project_id': 'p1', 'start': at('09:00'), 'end': null},
        }),
      ];

      expect(statusWith(running('p1', at('09:00')), queue, projects)['since'], at('08:30'));

      queue.add(stop(at('11:00'), project: 'p1', since: at('08:30')));
      expect(statusWith(running('p1', at('09:00')), queue, projects), {'isBeating': false});
    });
  });

  group('beatsWith', () {
    Map<String, dynamic> beat(String id, String project, String start, String? end) =>
        {'id': id, 'project_id': project, 'start': start, 'end': end};

    test('a start or a session logged offline appears once, without an id', () {
      final s = start('p1', at('09:00'));
      final log = write(WriteKind.log, {'project_id': 'p2', 'start': at('07:00'), 'end': at('08:00')});

      final beats = beatsWith([], [s, log]);

      expect(beats.map((b) => (b['id'], b['queued'], b['project_id'])), [(null, s.id, 'p1'), (null, log.id, 'p2')]);
    });

    test('a start already in the answer is not added again', () {
      final landed = [beat('b1', 'p1', '2026-10-14T09:00:00.000+00:00', null)];

      expect(beatsWith(landed, [start('p1', at('09:00'))]), landed);
    });

    test('a stop closes the session it names and no other', () {
      final queue = [stop(at('11:00'), project: 'p1', since: at('09:00'))];

      expect(beatsWith([beat('b1', 'p1', at('09:00'), null)], queue).single['end'], at('11:00'));
      expect(beatsWith([beat('b2', 'p1', at('10:00'), null)], queue).single['end'], isNull);
    });

    test('an edit applies only while the session is as it was when the edit was made', () {
      final edit = write(WriteKind.edit, {
        'id': 'b1',
        'project_id': 'p1',
        'start': at('08:30'),
        'end': at('10:00'),
        'expected': {'project_id': 'p1', 'start': at('09:00'), 'end': at('10:00')},
      });

      expect(beatsWith([beat('b1', 'p1', at('09:00'), at('10:00'))], [edit]).single['start'], at('08:30'));

      // Changed on the web meanwhile: the edit would be refused, so it shows nothing.
      expect(beatsWith([beat('b1', 'p1', at('09:00'), at('10:30'))], [edit]).single['start'], at('09:00'));

      // Deleted elsewhere: the edit doesn't bring it back.
      expect(beatsWith([], [edit]), isEmpty);
    });
  });
}
