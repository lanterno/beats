/// How durations and times of day read across the app: "3h 04m" for
/// totals, "1:24:07" for a running clock, "9:41" for a time of day.
library;

/// A total: "0m", "25m", "3h", "3h 04m". Minutes are padded once there are
/// hours so a column of totals lines up.
String formatMinutes(int minutes) {
  if (minutes <= 0) return '0m';
  final h = minutes ~/ 60;
  final m = minutes % 60;
  if (h == 0) return '${m}m';
  if (m == 0) return '${h}h';
  return '${h}h ${m.toString().padLeft(2, '0')}m';
}

String formatDuration(Duration d) => formatMinutes(d.isNegative ? 0 : d.inMinutes);

/// A running clock: "24:07" under an hour, "1:24:07" from there. Negative
/// durations (client/server clock skew) read as "0:00".
String formatClock(Duration d) {
  if (d.isNegative) return '0:00';
  final h = d.inHours;
  final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
  final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
  return h > 0 ? '$h:$m:$s' : '${d.inMinutes}:$s';
}

/// The menu bar's short clock: "24m" under an hour, "1:24" from there.
String formatShortClock(Duration d) {
  if (d.isNegative) return '0m';
  final h = d.inHours;
  if (h == 0) return '${d.inMinutes}m';
  return '$h:${d.inMinutes.remainder(60).toString().padLeft(2, '0')}';
}

/// A local time of day on the 24-hour clock: "9:41", "13:00".
String formatTimeOfDay(DateTime t) {
  final local = t.toLocal();
  return '${local.hour}:${local.minute.toString().padLeft(2, '0')}';
}

/// A signed balance in hours, as the web's ledger shows it: "+1h 10m",
/// "−25m", "±0m".
String formatBalance(double hours) {
  final minutes = (hours * 60).round();
  if (minutes == 0) return '±0m';
  final sign = minutes > 0 ? '+' : '−';
  return '$sign${formatMinutes(minutes.abs())}';
}
