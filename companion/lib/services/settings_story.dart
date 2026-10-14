/// What Settings says about the things it can only observe: how long ago
/// the daemon last reported, how many editor workspaces are sending, and a
/// short reason when a server call fails.
library;

import 'api_client.dart';

/// The newest `window_end` among [windows], or null when none parses.
DateTime? newestWindowEnd(List<Map<String, dynamic>> windows) {
  DateTime? newest;
  for (final w in windows) {
    final t = DateTime.tryParse(w['window_end'] as String? ?? '');
    if (t != null && (newest == null || t.isAfter(newest))) newest = t;
  }
  return newest;
}

/// "just now", "45s ago", "3m ago", "2h ago". A time ahead of [now]
/// (clock skew between this Mac and the server) reads as "just now".
String signalAgo(DateTime then, DateTime now) {
  final d = now.toUtc().difference(then.toUtc());
  if (d.inSeconds < 5) return 'just now';
  if (d.inSeconds < 60) return '${d.inSeconds}s ago';
  if (d.inMinutes < 60) return '${d.inMinutes}m ago';
  return '${d.inHours}h ago';
}

/// How many distinct editor workspaces (repos) appear in [windows].
int workspaceCount(List<Map<String, dynamic>> windows) => {
      for (final w in windows)
        if (w['editor_repo'] is String && (w['editor_repo'] as String).trim().isNotEmpty)
          (w['editor_repo'] as String).trim(),
    }.length;

/// True when [e] is the API refusing this device the path — an older server
/// that predates the paths the redesigned app reads.
bool needsNewerServer(Object e) => e is ApiException && e.statusCode == 403;

/// A failure short enough for a row's subtitle: the API's own sentence
/// without the "X failed:" prefix, cut at [max] characters.
String shortError(Object e, {int max = 80}) {
  var text = e is ApiException ? e.message : e.toString();
  final colon = text.indexOf(': ');
  if (e is ApiException && colon >= 0) text = text.substring(colon + 2);
  text = text.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (text.length <= max) return text;
  return '${text.substring(0, max - 1).trimRight()}…';
}
