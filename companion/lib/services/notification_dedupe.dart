import 'package:shared_preferences/shared_preferences.dart';

import 'notification_dedupe_ring.dart';

/// Per-kind, per-id dedupe for one-shot notifications. Used by
/// [NotificationPoller] so the same brief / review / drift / auto-timer
/// notification never fires twice even if the foreground poller hits
/// multiple times.
///
/// Storage shape: one SharedPreferences key per kind
/// (`beats_notified_brief`, `beats_notified_drift`, …) holding a bounded,
/// newest-last list of recently notified ids. New tick → look up the key →
/// if the current id is in the list, skip. After firing, append the id and
/// evict the oldest if the per-kind cap is exceeded.
///
/// Why a bounded list per kind (not a single id, not an unbounded set):
/// list-shaped kinds (drift, auto-timer) return up to ~20 events per tick.
/// Storing only the last id would let every *other* still-present event
/// re-fire on the next tick. A single id per kind also can't model that.
/// The cap keeps the key from growing forever while comfortably covering
/// the API page size; the oldest ids fall off, which is harmless because
/// the API only returns recent events anyway.
class NotificationDedupe {
  static const _prefix = 'beats_notified_';

  /// Max recent ids retained per kind. The API returns at most ~20 events
  /// per list-kind tick, so this leaves headroom across a couple of ticks
  /// before the oldest entries are evicted.
  static const _maxPerKind = 64;

  /// Returns true if [kind, id] has been seen before. Uses the singleton
  /// SharedPreferences instance so calls from different parts of the app
  /// see each other's writes.
  Future<bool> alreadyNotified(String kind, String id) async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList('$_prefix$kind') ?? const [];
    return stored.contains(id);
  }

  /// Records that we've notified for [kind, id]. Subsequent calls to
  /// [alreadyNotified] with the same arguments will return true. Re-marking
  /// an id already present moves it to newest, and the list is capped so it
  /// can't grow without bound.
  Future<void> markNotified(String kind, String id) async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList('$_prefix$kind') ?? const [];
    final next = appendBounded(stored, id, _maxPerKind);
    await prefs.setStringList('$_prefix$kind', next);
  }
}
