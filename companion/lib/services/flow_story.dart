/// Reads a day of the daemon's flow windows into what the Flow screen says:
/// five-minute bars with what you were doing in each, the best stretch of
/// flow as a sentence, minutes in flow, and where attention went in
/// percentages that add up. Pure, so the edge cases (gaps, ties, an empty
/// day, a stretch still running at the end of the day, rounding) are
/// tested without drawing anything.
library;

import 'time_format.dart';

/// The score at and above which a minute counts as flow — the line the
/// chart draws and the web's Insights use.
const flowLine = 0.7;

/// One of the daemon's one-minute windows.
class FlowSample {
  final DateTime start;
  final DateTime end;
  final double score;
  final String? repo;
  final String? language;
  final String? bundle;

  const FlowSample({
    required this.start,
    required this.end,
    required this.score,
    this.repo,
    this.language,
    this.bundle,
  });

  /// Parses a `/api/signals/flow-windows` row, or null when it has no
  /// start or no score. A missing end reads as one minute after the start.
  static FlowSample? fromJson(Map<String, dynamic> j) {
    final start = DateTime.tryParse(j['window_start'] as String? ?? '');
    final score = j['flow_score'];
    if (start == null || score is! num) return null;
    final end = DateTime.tryParse(j['window_end'] as String? ?? '') ?? start.add(const Duration(minutes: 1));
    String? text(Object? v) => v is String && v.isNotEmpty ? v : null;
    return FlowSample(
      start: start.toLocal(),
      end: end.toLocal(),
      score: score.toDouble().clamp(0.0, 1.0),
      repo: text(j['editor_repo']),
      language: text(j['editor_language']),
      bundle: text(j['dominant_bundle_id']),
    );
  }

  static List<FlowSample> listFrom(Iterable<Map<String, dynamic>> rows) =>
      rows.map(fromJson).whereType<FlowSample>().toList()..sort((a, b) => a.start.compareTo(b.start));
}

/// One bar of the chart. [score] is null when no window started in it.
class FlowBar {
  final DateTime start;
  final DateTime end;
  final double? score;
  final int count;
  final String? repo;
  final String? language;
  final String? bundle;

  const FlowBar({
    required this.start,
    required this.end,
    this.score,
    this.count = 0,
    this.repo,
    this.language,
    this.bundle,
  });
}

/// The most common non-null value, the first seen winning a tie.
String? _dominant(Iterable<String?> values) {
  final counts = <String, int>{};
  for (final v in values) {
    if (v != null) counts[v] = (counts[v] ?? 0) + 1;
  }
  String? best;
  var bestCount = 0;
  for (final e in counts.entries) {
    if (e.value > bestCount) {
      best = e.key;
      bestCount = e.value;
    }
  }
  return best;
}

/// Buckets [samples] (sorted, local times) into bars of [width] from the
/// hour of the first window to the end of the hour of the last.
List<FlowBar> flowBars(List<FlowSample> samples, {Duration width = const Duration(minutes: 5)}) {
  if (samples.isEmpty) return const [];
  final first = samples.first.start;
  final last = samples.last.start;
  final from = DateTime(first.year, first.month, first.day, first.hour);
  final to = DateTime(last.year, last.month, last.day, last.hour + 1);
  final n = to.difference(from).inMinutes ~/ width.inMinutes;
  final buckets = List.generate(n, (_) => <FlowSample>[]);
  for (final s in samples) {
    final i = s.start.difference(from).inMinutes ~/ width.inMinutes;
    if (i >= 0 && i < n) buckets[i].add(s);
  }
  return [
    for (var i = 0; i < n; i++)
      FlowBar(
        start: from.add(width * i),
        end: from.add(width * (i + 1)),
        score: buckets[i].isEmpty
            ? null
            : buckets[i].map((s) => s.score).reduce((a, b) => a + b) / buckets[i].length,
        count: buckets[i].length,
        repo: _dominant(buckets[i].map((s) => s.repo)),
        language: _dominant(buckets[i].map((s) => s.language)),
        bundle: _dominant(buckets[i].map((s) => s.bundle)),
      ),
  ];
}

/// An unbroken run of windows at or above [flowLine].
class FlowStretch {
  final DateTime start;
  final DateTime end;
  final double average;
  final String? repo;
  const FlowStretch(this.start, this.end, this.average, this.repo);

  Duration get length => end.difference(start);
}

/// The longest run of flow windows, where neighbours more than [maxGap]
/// apart break the run. Ties go to the higher average, then the earlier.
/// Null when no window reaches the flow line.
FlowStretch? bestStretch(List<FlowSample> samples, {Duration maxGap = const Duration(minutes: 2)}) {
  FlowStretch? best;
  var run = <FlowSample>[];

  void close() {
    if (run.isEmpty) return;
    final avg = run.map((s) => s.score).reduce((a, b) => a + b) / run.length;
    final candidate = FlowStretch(run.first.start, run.last.end, avg, _dominant(run.map((s) => s.repo)));
    if (best == null ||
        candidate.length > best!.length ||
        (candidate.length == best!.length && candidate.average > best!.average)) {
      best = candidate;
    }
    run = [];
  }

  for (final s in samples) {
    if (s.score < flowLine) {
      close();
      continue;
    }
    if (run.isNotEmpty && s.start.difference(run.last.end) > maxGap) close();
    run.add(s);
  }
  close();
  return best;
}

/// The day's headline: its best stretch when one lasted [minimum], else
/// when its best minutes came.
String flowHeadline(List<FlowSample> samples, {required bool today, Duration minimum = const Duration(minutes: 5)}) {
  final stretch = bestStretch(samples);
  if (stretch != null && stretch.length >= minimum) {
    final where = stretch.repo == null ? '' : ', in ${stretch.repo}';
    return 'Your best stretch was ${formatTimeOfDay(stretch.start)} to ${formatTimeOfDay(stretch.end)}$where.';
  }
  final when = today ? 'yet today' : 'that day';
  final peak = peakSample(samples);
  if (peak == null) return 'No flow $when.';
  return 'No long stretch of flow $when. Your best minute came at ${formatTimeOfDay(peak.start)}.';
}

/// The window with the highest score, the earliest winning a tie.
FlowSample? peakSample(List<FlowSample> samples) {
  FlowSample? best;
  for (final s in samples) {
    if (best == null || s.score > best.score) best = s;
  }
  return best;
}

double? averageScore(List<FlowSample> samples) {
  if (samples.isEmpty) return null;
  return samples.map((s) => s.score).reduce((a, b) => a + b) / samples.length;
}

/// Time spent at or above the flow line.
Duration timeInFlow(Iterable<FlowSample> samples) => samples
    .where((s) => s.score >= flowLine)
    .fold(Duration.zero, (a, s) => a + s.end.difference(s.start));

/// Time in flow per value of [key] (a repo, a language, an app).
Map<String, Duration> timeInFlowBy(Iterable<FlowSample> samples, String? Function(FlowSample) key) {
  final out = <String, Duration>{};
  for (final s in samples) {
    final k = key(s);
    if (k == null || s.score < flowLine) continue;
    out[k] = (out[k] ?? Duration.zero) + s.end.difference(s.start);
  }
  return out;
}

/// A line comparing [avg] with yesterday's, or null without one.
String? comparedWithYesterday(int avg, int? yesterday) {
  if (yesterday == null) return null;
  final d = avg - yesterday;
  if (d == 0) return 'The same average as yesterday.';
  final points = d.abs() == 1 ? 'point' : 'points';
  return '${d.abs()} $points ${d > 0 ? 'above' : 'below'} yesterday\'s $yesterday.';
}

/// Category shares as whole percentages that add up to 100 (largest
/// remainder), biggest first. Categories with no samples, or whose share
/// rounds to nothing, are left out.
List<(String, int)> categoryShares(Map<String, int> totals) {
  final entries = totals.entries.where((e) => e.value > 0).toList();
  final sum = entries.fold<int>(0, (a, e) => a + e.value);
  if (sum == 0) return const [];
  final exact = [for (final e in entries) (e.key, e.value * 100 / sum)];
  final floors = {for (final (k, v) in exact) k: v.floor()};
  var left = 100 - floors.values.fold<int>(0, (a, b) => a + b);
  final byRemainder = [...exact]
    ..sort((a, b) {
      final r = (b.$2 - b.$2.floor()).compareTo(a.$2 - a.$2.floor());
      return r != 0 ? r : b.$2.compareTo(a.$2);
    });
  for (final (k, _) in byRemainder) {
    if (left == 0) break;
    floors[k] = floors[k]! + 1;
    left--;
  }
  final shares = [
    for (final e in floors.entries)
      if (e.value > 0) (e.key, e.value),
  ]..sort((a, b) => b.$2.compareTo(a.$2));
  return shares;
}
