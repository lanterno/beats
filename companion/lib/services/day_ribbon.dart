/// The geometry of Today's "Your day" strip: which hours it spans, where
/// each session and calendar event sits on it, and the flow score per
/// quarter hour. Pure, so the arithmetic (clamping, a session running past
/// the edge, an empty quarter) is tested without drawing anything.
library;

/// The stretch of one local day the strip shows.
class DayWindow {
  final DateTime start;
  final DateTime end;
  const DayWindow(this.start, this.end);

  Duration get length => end.difference(start);

  /// Where [t] falls, 0 at [start] and 1 at [end], clamped.
  double fractionOf(DateTime t) {
    final f = t.difference(start).inSeconds / length.inSeconds;
    return f.clamp(0.0, 1.0);
  }

  /// Whole local hours from start to end, every [step] hours.
  List<int> hourTicks({int step = 2}) {
    final ticks = <int>[];
    for (var t = start; !t.isAfter(end); t = t.add(Duration(hours: step))) {
      ticks.add(t.hour);
    }
    return ticks;
  }
}

/// The strip's hours for [day]: 7:00 to 20:00, widened to whole hours so
/// every one of [marks] (session and event edges, now) is on it, and never
/// past the day's midnights.
DayWindow dayWindowFor(DateTime day, Iterable<DateTime> marks, {int fromHour = 7, int toHour = 20}) {
  final midnight = DateTime(day.year, day.month, day.day);
  final nextMidnight = DateTime(day.year, day.month, day.day + 1);
  var from = fromHour, to = toHour;
  for (final m in marks) {
    final local = m.toLocal();
    if (local.isBefore(midnight)) {
      from = 0;
    } else if (!local.isBefore(nextMidnight)) {
      to = 24;
    } else {
      if (local.hour < from) from = local.hour;
      final ceil = local.minute > 0 || local.second > 0 ? local.hour + 1 : local.hour;
      if (ceil > to) to = ceil;
    }
  }
  return DayWindow(
    DateTime(day.year, day.month, day.day, from),
    to >= 24 ? nextMidnight : DateTime(day.year, day.month, day.day, to),
  );
}

/// Something laid on the strip: [left] and [width] are fractions of it.
class Placed<T> {
  final double left;
  final double width;
  final T item;
  const Placed(this.left, this.width, this.item);
}

/// Places each span on [w], clipping the parts outside it and dropping
/// spans entirely outside. A span with no end (the running timer) runs to
/// [now].
List<Placed<T>> placeSpans<T>(
  DayWindow w,
  Iterable<(DateTime start, DateTime? end, T item)> spans, {
  required DateTime now,
}) {
  final placed = <Placed<T>>[];
  for (final (start, end, item) in spans) {
    final a = w.fractionOf(start);
    final b = w.fractionOf(end ?? now);
    if (b - a <= 0) continue;
    placed.add(Placed(a, b - a, item));
  }
  return placed;
}

/// The average flow score in each [bucket] across [w], null where no window
/// started. Windows are (start, score 0–1).
List<double?> flowBuckets(
  DayWindow w,
  Iterable<(DateTime, double)> windows, {
  Duration bucket = const Duration(minutes: 15),
}) {
  final n = (w.length.inMinutes / bucket.inMinutes).ceil();
  final sums = List<double>.filled(n, 0);
  final counts = List<int>.filled(n, 0);
  for (final (start, score) in windows) {
    final offset = start.difference(w.start);
    if (offset.isNegative || !start.isBefore(w.end)) continue;
    final i = offset.inMinutes ~/ bucket.inMinutes;
    sums[i] += score;
    counts[i]++;
  }
  return [for (var i = 0; i < n; i++) counts[i] == 0 ? null : sums[i] / counts[i]];
}

/// The opening of a coach brief for a card: markdown marks taken out, cut at
/// a sentence end before [max] characters (or at a word, with an ellipsis,
/// when the first sentence alone is longer).
String? briefExcerpt(String? body, {int max = 220}) {
  if (body == null) return null;
  final plain = body
      .split('\n')
      .map((l) => l.replaceFirst(RegExp(r'^\s*(#+|[-*]|\d+\.)\s+'), ''))
      .join(' ')
      .replaceAll(RegExp(r'[*_`]'), '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (plain.isEmpty) return null;
  if (plain.length <= max) return plain;
  final window = plain.substring(0, max);
  final sentenceEnd = RegExp(r'[.!?](?=\s)').allMatches(window).lastOrNull;
  if (sentenceEnd != null) return window.substring(0, sentenceEnd.end);
  final space = window.lastIndexOf(' ');
  return '${window.substring(0, space > 0 ? space : max).trimRight()}…';
}
