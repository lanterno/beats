import 'offline_queue.dart';

/// The timer and the sessions as this device has them: the API's last
/// answer with the writes still waiting applied on top, by the API's own
/// rules (docs/companion-offline.md). Each step is a no-op when the answer
/// already holds it, so a write that has landed but not yet left the queue
/// is never counted twice.

/// Equal to the millisecond, the precision the API stores; [a] and [b] are
/// ISO strings, DateTimes or null.
bool sameInstant(Object? a, Object? b) {
  DateTime? parse(Object? v) => v is DateTime ? v : (v is String ? DateTime.tryParse(v) : null);
  final x = parse(a), y = parse(b);
  if (x == null || y == null) return x == null && y == null;
  return x.millisecondsSinceEpoch == y.millisecondsSinceEpoch;
}

/// `GET /api/timer/status` with [queue] applied. [projects] lends a started
/// project its name and colour.
Map<String, dynamic> statusWith(
  Map<String, dynamic> status,
  Iterable<QueuedWrite> queue,
  List<Map<String, dynamic>> projects,
) {
  var running = status['isBeating'] == true && status['since'] != null;
  var project = status['project'] as Map<String, dynamic>?;
  var since = status['since'] as Object?;
  var changed = false;

  bool runs(Object? expected) {
    if (!running || expected is! Map) return false;
    return project?['id'] == expected['project_id'] && sameInstant(since, expected['start']);
  }

  Map<String, dynamic> projectOf(Object? id) =>
      projects.where((p) => p['id'] == id).firstOrNull ?? {'id': id, 'name': 'Untitled'};

  for (final w in queue) {
    final b = w.body;
    switch (w.kind) {
      case WriteKind.start:
        // The API refuses a start while something runs; so does the view.
        if (running) continue;
        (running, project, since, changed) = (true, projectOf(b['project_id']), b['time'], true);
      case WriteKind.stop:
        if (!runs(b['expected'])) continue;
        (running, changed) = (false, true);
      case WriteKind.edit:
        final e = b['expected'];
        if (e is! Map || e['end'] != null || !runs(e)) continue;
        if (b['end'] == null) {
          (project, since, changed) = (projectOf(b['project_id']), b['start'], true);
        } else {
          (running, changed) = (false, true);
        }
      case WriteKind.log:
        continue;
    }
  }
  if (!changed) return status;
  if (!running) return {'isBeating': false};
  return {...status, 'isBeating': true, 'project': project, 'since': since};
}

/// Sessions as `GET /api/beats/` returns them, with [queue] applied. A
/// session made here and not yet sent has no `id` and carries `queued`,
/// its write's row id. The caller files the result by start day: a moved
/// start can carry a session across one.
List<Map<String, dynamic>> beatsWith(List<Map<String, dynamic>> beats, Iterable<QueuedWrite> queue) {
  final out = [for (final b in beats) Map<String, dynamic>.of(b)];

  bool matches(Map<String, dynamic> beat, Object? expected) =>
      expected is Map &&
      beat['project_id'] == expected['project_id'] &&
      sameInstant(beat['start'], expected['start']) &&
      sameInstant(beat['end'], expected['end']);

  for (final w in queue) {
    final b = w.body;
    switch (w.kind) {
      case WriteKind.start:
        final there = out.any((x) => x['project_id'] == b['project_id'] && sameInstant(x['start'], b['time']));
        if (!there) out.add(w.placeholder(w.id ?? 0));
      case WriteKind.stop:
        final e = b['expected'] as Map?;
        final open = out.where((x) => x['end'] == null && matches(x, e)).firstOrNull;
        if (open != null) open['end'] = b['time'];
      case WriteKind.log:
        final there = out.any((x) =>
            x['project_id'] == b['project_id'] && sameInstant(x['start'], b['start']) && sameInstant(x['end'], b['end']));
        if (!there) out.add(w.placeholder(w.id ?? 0));
      case WriteKind.edit:
        final x = out.where((x) => x['id'] != null && x['id'] == b['id']).firstOrNull;
        if (x == null || !matches(x, b['expected'])) continue;
        x
          ..['project_id'] = b['project_id']
          ..['start'] = b['start']
          ..['end'] = b['end'];
    }
  }
  return out;
}
