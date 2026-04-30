import 'package:shared_preferences/shared_preferences.dart';

/// Per-kind, per-id dedupe for one-shot notifications. Used by
/// [NotificationPoller] so the same brief / review never fires twice in
/// the same day even if the foreground poller hits multiple times.
///
/// Storage shape: one SharedPreferences key per kind
/// (`beats_notified_brief`, `beats_notified_review`, …) holding the id
/// of the last notified item. New tick → look up the key → if the
/// current id matches, skip. After firing, write the id.
///
/// Why one key per kind (not a set of all-time-seen ids): deletes are
/// implicit. Tomorrow's brief id will be different; storing today's id
/// against `beats_notified_brief` is enough to suppress today's reruns
/// without growing forever.
class NotificationDedupe {
  static const _prefix = 'beats_notified_';

  /// Returns true if [kind, id] has been seen before. Uses the singleton
  /// SharedPreferences instance so calls from different parts of the app
  /// see each other's writes.
  Future<bool> alreadyNotified(String kind, String id) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('$_prefix$kind') == id;
  }

  /// Records that we've notified for [kind, id]. Subsequent calls to
  /// [alreadyNotified] with the same arguments will return true.
  Future<void> markNotified(String kind, String id) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('$_prefix$kind', id);
  }
}
