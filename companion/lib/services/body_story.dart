/// Reads a week of `/api/biometrics` days into what the Body screen and
/// Today's body card say: the latest value of each measure, its series and
/// average, and a sentence for readiness.
library;

class BodyWeek {
  /// Days oldest first, as the API returns them (one per date and source).
  final List<Map<String, dynamic>> days;
  const BodyWeek(this.days);

  bool get isEmpty => days.isEmpty;

  /// The newest non-null value of [field], or null.
  num? latest(String field) {
    for (final d in days.reversed) {
      final v = d[field];
      if (v is num) return v;
    }
    return null;
  }

  /// Every non-null value of [field], oldest first.
  List<double> series(String field) => [
        for (final d in days)
          if (d[field] is num) (d[field] as num).toDouble(),
      ];

  double? average(String field) {
    final s = series(field);
    if (s.isEmpty) return null;
    return s.reduce((a, b) => a + b) / s.length;
  }

  /// Where the data comes from, as a person would name it: "Oura",
  /// "Oura and Fitbit".
  String? get sources {
    final names = <String>{
      for (final d in days)
        if (d['source'] is String && (d['source'] as String).isNotEmpty) _sourceName(d['source'] as String),
    }.toList();
    if (names.isEmpty) return null;
    if (names.length == 1) return names.first;
    return '${names.sublist(0, names.length - 1).join(', ')} and ${names.last}';
  }

  /// The value of [field] on [date] (`YYYY-MM-DD`), from whichever source
  /// recorded it; the later entry wins when two did.
  num? on(String date, String field) {
    num? found;
    for (final d in days) {
      if (d['date'] == date && d[field] is num) found = d[field] as num;
    }
    return found;
  }

  /// When the newest entry reached the server, or null.
  DateTime? get lastSynced {
    DateTime? newest;
    for (final d in days) {
      final t = DateTime.tryParse(d['created_at'] as String? ?? '');
      if (t != null && (newest == null || t.isAfter(newest))) newest = t;
    }
    return newest;
  }
}

String _sourceName(String s) => switch (s) {
      'oura' => 'Oura',
      'fitbit' => 'Fitbit',
      'healthkit' => 'Apple Health',
      'health_connect' => 'Health Connect',
      _ => s,
    };

/// One line on what a readiness score means for the day ahead.
String readinessLine(int score) {
  if (score >= 85) return 'Fully recovered. A good day for your hardest work.';
  if (score >= 70) return 'Recovered. A good day for a long block.';
  if (score >= 60) return 'Steady. Keep the blocks shorter and the breaks real.';
  return 'Running low. Plan lighter work and an early night.';
}

/// Sleep minutes as "7h 24m".
String formatSleep(num minutes) {
  final m = minutes.round();
  return '${m ~/ 60}h ${(m % 60).toString().padLeft(2, '0')}m';
}

const _numberWords = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];

String _count(int n) => n < _numberWords.length ? _numberWords[n] : '$n';

/// How the newest HRV and resting heart rate sit against their averages
/// over the week: "HRV is above your seven-day average and resting heart
/// rate is down two beats." HRV within 5% of its average reads as "close
/// to"; a resting rate within half a beat as "level". Null without either.
String? recoveryLine(BodyWeek week) {
  final parts = <String>[];
  final hrv = week.latest('hrv_ms');
  final hrvAvg = week.average('hrv_ms');
  if (hrv != null && hrvAvg != null && hrvAvg > 0) {
    final ratio = hrv / hrvAvg;
    final where = ratio > 1.05
        ? 'above'
        : ratio < 0.95
            ? 'below'
            : 'close to';
    parts.add('HRV is $where your seven-day average');
  }
  final rhr = week.latest('resting_hr_bpm');
  final rhrAvg = week.average('resting_hr_bpm');
  if (rhr != null && rhrAvg != null) {
    final delta = (rhr - rhrAvg).round();
    final beats = delta.abs() == 1 ? 'beat' : 'beats';
    parts.add(delta == 0
        ? 'resting heart rate is level'
        : 'resting heart rate is ${delta < 0 ? 'down' : 'up'} ${_count(delta.abs())} $beats');
  }
  if (parts.isEmpty) return null;
  final line = parts.join(' and ');
  return '${line[0].toUpperCase()}${line.substring(1)}.';
}

/// Steps as "7,560".
String formatSteps(num steps) {
  final digits = steps.round().toString();
  final out = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) out.write(',');
    out.write(digits[i]);
  }
  return out.toString();
}

/// The quiet line under a metric tile: the week's average, and for sleep
/// the newest night's efficiency first. Null when the week has no data.
String? metricNote(BodyWeek week, String field) {
  final avg = week.average(field);
  if (avg == null) return null;
  switch (field) {
    case 'sleep_minutes':
      final eff = week.latest('sleep_efficiency');
      if (eff == null) return 'Week avg ${formatSleep(avg)}';
      // Efficiency arrives as 0–1; a source that sends a percentage is
      // shown as it is.
      final pct = eff <= 1 ? (eff * 100).round() : eff.round();
      return '$pct% efficient · week avg ${formatSleep(avg)}';
    case 'hrv_ms':
      return 'Week avg ${avg.round()} ms';
    case 'resting_hr_bpm':
      return 'Week avg ${avg.round()} bpm';
    case 'steps':
      return 'Week avg ${formatSteps(avg)}';
    default:
      return 'Week avg ${avg.round()}';
  }
}

/// One night's sleep beside the next day's average flow (0–100). The
/// biometrics `date` is the day the sleep ended on, so it pairs with that
/// same day's flow.
class SleepFlowPair {
  final DateTime day;
  final double? sleepHours;
  final int? flow;
  const SleepFlowPair(this.day, this.sleepHours, this.flow);
}

/// Pairs each of [days] (local midnights, oldest first) with its night's
/// sleep from [week] and its flow average from [flowByDate] (`YYYY-MM-DD`).
List<SleepFlowPair> pairSleepWithFlow(
  BodyWeek week,
  Map<String, int> flowByDate,
  List<DateTime> days,
) {
  String key(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  return days.map((d) {
    final minutes = week.on(key(d), 'sleep_minutes');
    return SleepFlowPair(d, minutes == null ? null : minutes / 60, flowByDate[key(d)]);
  }).toList();
}

/// "After nights over seven hours your flow averaged 72. Under six, it was
/// 58." Only when both kinds of night have a day of flow after them;
/// otherwise null.
String? sleepFlowLine(List<SleepFlowPair> pairs) {
  int? avg(Iterable<SleepFlowPair> ps) {
    final flows = [for (final p in ps) if (p.flow != null) p.flow!];
    if (flows.isEmpty) return null;
    return (flows.reduce((a, b) => a + b) / flows.length).round();
  }

  final long = avg(pairs.where((p) => p.sleepHours != null && p.sleepHours! >= 7));
  final short = avg(pairs.where((p) => p.sleepHours != null && p.sleepHours! < 6));
  if (long == null || short == null) return null;
  return 'After nights over seven hours your flow averaged $long. Under six, it was $short.';
}
