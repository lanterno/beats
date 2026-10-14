/// The rules for logging a session after the fact: what makes a "from" and
/// "to" a session worth sending. Pure, so the edges (midnight, the running
/// timer, touching but not overlapping) are tested.
library;

import 'time_format.dart';

/// A session already on the day: [end] is null while it runs.
class DaySpan {
  final DateTime start;
  final DateTime? end;
  final String project;
  const DaySpan(this.start, this.end, this.project);
}

/// Why [start]–[end] can't be logged as it stands, or null when it can.
/// Sessions may touch (one ending at 10:30, the next starting at 10:30) but
/// not overlap; a running session runs to [now].
String? pastSessionProblem(
  DateTime start,
  DateTime end,
  DateTime now, {
  List<DaySpan> existing = const [],
}) {
  if (!end.isAfter(start)) return 'The end has to come after the start.';
  if (end.isAfter(now)) return 'That ends in the future — start a timer instead.';
  if (end.difference(start) > const Duration(hours: 16)) return 'That is longer than 16 hours.';
  for (final s in existing) {
    final sEnd = s.end ?? now;
    if (start.isBefore(sEnd) && end.isAfter(s.start)) {
      return 'That overlaps ${formatTimeOfDay(s.start)}–'
          '${s.end == null ? 'now' : formatTimeOfDay(sEnd)} on ${s.project}.';
    }
  }
  return null;
}

/// [day] at [hour]:[minute], local; an end time at or before the start time
/// on the same day is read as running past midnight.
(DateTime, DateTime) sessionTimes(DateTime day, (int, int) from, (int, int) to) {
  final start = DateTime(day.year, day.month, day.day, from.$1, from.$2);
  var end = DateTime(day.year, day.month, day.day, to.$1, to.$2);
  if (!end.isAfter(start)) end = DateTime(day.year, day.month, day.day + 1, to.$1, to.$2);
  return (start, end);
}
