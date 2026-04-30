import 'package:shared_preferences/shared_preferences.dart';

/// Maintains a most-recently-used list of project IDs in SharedPreferences.
///
/// The companion uses this to render a "RECENT" section above the full project
/// list in the timer-screen picker. The API doesn't expose a per-project
/// last-used timestamp, so we track it locally — the cost of "wrong" recents
/// after a fresh device pair is minor (the list rebuilds within a day or two
/// of normal use).
class RecentProjects {
  static const _key = 'beats_recent_project_ids';
  static const _maxRecents = 5;

  Future<List<String>> load() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getStringList(_key) ?? const [];
  }

  /// Promotes [projectId] to the head of the list, deduping and capping length.
  Future<void> markUsed(String projectId) async {
    if (projectId.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    final current = prefs.getStringList(_key) ?? <String>[];
    final next = <String>[projectId, ...current.where((id) => id != projectId)];
    if (next.length > _maxRecents) next.removeRange(_maxRecents, next.length);
    await prefs.setStringList(_key, next);
  }
}
