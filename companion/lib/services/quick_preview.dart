/// The sentence a quick-start command shows before it runs: what Return (or
/// the sheet's button) is about to do, and to whom. Shared by the Mac
/// palette and the phone's start sheet so both describe a switch the same way.
///
/// Pure: names and times in, two lines out.
library;

import 'time_format.dart';

class QuickPreview {
  /// "Switch to Studio Kite from 11:00".
  final String title;

  /// The consequence: "Stops Northwind at 11:00 (1h 19m) · Studio Kite starts 5m ago".
  final String? detail;

  const QuickPreview(this.title, [this.detail]);
}

/// Starting [project] at [at] (null: now), while [running] has run since
/// [since] (both null when nothing runs). [same] says [project] is the one
/// running, which names alone can't.
QuickPreview previewStart({
  required String project,
  required DateTime now,
  DateTime? at,
  String? running,
  DateTime? since,
  bool same = false,
}) {
  final when = at == null ? '' : ' from ${formatTimeOfDay(at)}';
  if (running != null && since != null && !same) {
    final stopAt = at ?? now;
    final ran = stopAt.toUtc().difference(since.toUtc());
    return QuickPreview(
      'Switch to $project$when',
      'Stops $running${at == null ? '' : ' at ${formatTimeOfDay(at)}'} '
          '(${formatDuration(ran)})${at == null ? '' : ' · $project starts ${_ago(now.difference(at))}'}',
    );
  }
  if (same && at != null) {
    return QuickPreview('Restart $project$when', 'Closes the running session and opens a new one');
  }
  return QuickPreview('Start $project$when', at == null ? null : 'Starts ${_ago(now.difference(at))}');
}

/// Stopping [running], which has run since [since], at [at] (null: now).
QuickPreview previewStop({
  required String running,
  required DateTime since,
  required DateTime now,
  DateTime? at,
}) {
  final stopAt = at ?? now;
  return QuickPreview(
    'Stop $running${at == null ? '' : ' at ${formatTimeOfDay(at)}'}',
    'Logs ${formatDuration(stopAt.toUtc().difference(since.toUtc()))}',
  );
}

String _ago(Duration d) => d.inMinutes < 1 ? 'now' : '${formatDuration(d)} ago';
