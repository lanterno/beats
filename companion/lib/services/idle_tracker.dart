/// Turns a stream of "seconds since the last input" readings into the
/// stretches someone was away. Pure: the clock and the readings come in,
/// so the edges are testable without a Mac.
library;

class AwayPeriod {
  final DateTime from;
  final DateTime to;
  const AwayPeriod(this.from, this.to);
  Duration get length => to.difference(from);
}

class IdleTracker {
  /// How long without input counts as away.
  final Duration threshold;

  /// Input within this long counts as back.
  final Duration back;

  IdleTracker({this.threshold = const Duration(minutes: 10), this.back = const Duration(minutes: 1)});

  DateTime? _awaySince;

  bool get away => _awaySince != null;

  /// Feeds one reading: at [now], [idle] has passed since the last input.
  /// Returns the stretch away once input comes back after at least
  /// [threshold] without any; otherwise null.
  AwayPeriod? sample(DateTime now, Duration idle) {
    if (idle >= threshold) {
      // The stretch started at the last input, not at the reading.
      _awaySince ??= now.subtract(idle);
      return null;
    }
    final since = _awaySince;
    if (since != null && idle < back) {
      _awaySince = null;
      return AwayPeriod(since, now.subtract(idle));
    }
    return null;
  }

  /// Forgets a stretch in progress (the timer stopped, the setting went off).
  void reset() => _awaySince = null;
}
