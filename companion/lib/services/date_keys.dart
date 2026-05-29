/// Calendar-day helpers that step by date COMPONENTS, never by 24-hour
/// Duration arithmetic.
///
/// `someLocalDateTime.subtract(Duration(days: 1))` shifts by exactly 24h, but
/// a local day spanning a DST transition is 23h or 25h long — so the result
/// can land on the wrong calendar day and produce the wrong `YYYY-MM-DD` key.
/// `DateTime(y, m, d - 1)` always lands on the previous calendar day (local
/// midnight) regardless of DST, and normalizes month/year rollover.
library;

/// The `YYYY-MM-DD` key for a local date (matches the API's heatmap/day keys).
String dayKey(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// Local midnight of the calendar day `n` days from `d` (DST-safe; `n` may be
/// negative). Uses component math so a DST transition can't drop or duplicate
/// a day.
DateTime addDays(DateTime d, int n) => DateTime(d.year, d.month, d.day + n);

/// Today / this-week / last-week minutes and the current streak, computed from
/// a `YYYY-MM-DD` → minutes map (the indexed heatmap).
class TimerStats {
  final int todayMinutes;
  final int weekMinutes;
  final int lastWeekMinutes;
  final int streakDays;

  const TimerStats({
    required this.todayMinutes,
    required this.weekMinutes,
    required this.lastWeekMinutes,
    required this.streakDays,
  });
}

/// Compute timer stats for the day containing [today]. All day stepping uses
/// [addDays] so the week window, last-week window, and streak walk can't be
/// thrown off by a DST transition. The streak forgives a zero-minute *today*
/// (so it doesn't drop until the user has actually missed a day).
TimerStats computeTimerStats(Map<String, int> byDate, DateTime today) {
  int minutesOn(DateTime d) => byDate[dayKey(d)] ?? 0;

  final todayMid = DateTime(today.year, today.month, today.day);
  // Week = Monday→Sunday containing today (DateTime.weekday: Mon=1, Sun=7).
  final weekStart = addDays(todayMid, -(today.weekday - 1));

  var weekMins = 0;
  var lastWeekMins = 0;
  for (var i = 0; i < 7; i++) {
    weekMins += minutesOn(addDays(weekStart, i));
    lastWeekMins += minutesOn(addDays(weekStart, i - 7));
  }

  var streak = 0;
  var cursor = todayMid;
  var first = true;
  while (true) {
    if (minutesOn(cursor) > 0) {
      streak++;
    } else if (!first) {
      break;
    }
    first = false;
    cursor = addDays(cursor, -1);
    // Bound the walk to a year to avoid runaway loops on garbage data.
    if (todayMid.difference(cursor).inDays > 365) break;
  }

  return TimerStats(
    todayMinutes: minutesOn(todayMid),
    weekMinutes: weekMins,
    lastWeekMinutes: lastWeekMins,
    streakDays: streak,
  );
}
