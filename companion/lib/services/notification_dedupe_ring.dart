/// Pure helper for [NotificationDedupe]'s bounded per-kind id list.
///
/// Extracted from the SharedPreferences-backed dedupe so the
/// append/dedup/evict rules can be unit-tested without a prefs instance —
/// mirrors the pure-helper-with-parity-tests pattern used by
/// `flow_summary.dart`.
library;

/// Appends [id] to [current] (a newest-last list of seen ids), keeping at
/// most [cap] entries.
///
/// - If [id] is already present it is moved to the newest position rather
///   than duplicated, so re-marking refreshes recency (LRU-style).
/// - When the result would exceed [cap], the oldest ids (front of the
///   list) are dropped. This bounds storage growth while always retaining
///   the most recently seen ids — the ones a re-poll is most likely to
///   surface again.
///
/// Returns a new list; [current] is not mutated.
List<String> appendBounded(List<String> current, String id, int cap) {
  // Drop any existing occurrence so the id re-enters as newest.
  final next = [
    for (final existing in current)
      if (existing != id) existing,
    id,
  ];
  if (cap <= 0) return const [];
  if (next.length <= cap) return next;
  return next.sublist(next.length - cap);
}
