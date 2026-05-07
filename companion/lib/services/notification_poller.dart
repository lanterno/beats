import 'dart:async';

import 'api_client.dart';
import 'notification_dedupe.dart';
import 'notifications.dart';

/// Foreground polling loop that converts API state into local notifications.
///
/// Runs while the app is alive (foreground or backgrounded but not yet
/// terminated by the OS). Each tick, polls the coach endpoints and fires
/// notifications when something new is available, deduped per-day via
/// SharedPreferences so the user never sees the same brief twice.
///
/// **Limitations of the free-tier path**: this is *not* true server-pushed
/// delivery. If the user closes the app and the coach generates a brief at
/// 7 AM, they won't see the notification until they reopen. Pair this with
/// [NotificationsService.scheduleEodMoodPrompt] for the EOD reminder, which
/// fires from the OS-level scheduler regardless of app state.
class NotificationPoller {
  final ApiClient client;
  final NotificationsService notifications;
  Duration interval;
  final NotificationDedupe _dedupe;

  NotificationPoller({
    required this.client,
    required this.notifications,
    this.interval = const Duration(minutes: 5),
    NotificationDedupe? dedupe,
  }) : _dedupe = dedupe ?? NotificationDedupe();

  Timer? _timer;
  bool _running = false;

  void start() {
    if (_timer != null) return;
    // Tick once immediately so the user sees today's pending brief / review
    // shortly after the app is opened, then on the configured cadence.
    unawaited(_tick());
    _timer = Timer.periodic(interval, (_) => _tick());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _tick() async {
    if (_running) return; // prevent overlap if a previous tick is still in flight
    _running = true;
    try {
      await Future.wait([
        _pollBrief(),
        _pollReview(),
        _pollDrift(),
        _pollAutoTimer(),
      ]);
    } finally {
      _running = false;
    }
  }

  Future<void> _pollBrief() async {
    try {
      final brief = await client.getTodayBrief();
      if (brief == null) return;
      final id = (brief['id'] as String?) ?? (brief['date'] as String?);
      if (id == null) return;
      if (await _dedupe.alreadyNotified('brief', id)) return;
      await notifications.notifyBriefAvailable(
          preview: briefPreview(brief['body'] as String?));
      await _dedupe.markNotified('brief', id);
    } catch (_) {
      // Network blips, daemon offline, etc. — silent, retry next tick.
    }
  }

  Future<void> _pollReview() async {
    try {
      final review = await client.getTodayReview();
      if (review == null) return;
      final date = review['date'] as String?;
      if (date == null) return;
      if (await _dedupe.alreadyNotified('review', date)) return;
      await notifications.notifyReviewAvailable();
      await _dedupe.markNotified('review', date);
    } catch (_) {
      // Same as above — best-effort.
    }
  }

  /// Polls `/api/signals/recent-drift` and fires a drift notification for
  /// every event id we haven't seen. Dedupe keys live in SharedPreferences
  /// so the user doesn't see the same drift twice if the poller restarts.
  ///
  /// The daemon already fires native macOS notifications via osascript on
  /// the desktop; this companion-side path covers iOS / Android and any
  /// desktop where the daemon isn't installed. Both paths firing in
  /// parallel is fine — they target different channels (OS-level
  /// notification center vs Beats' in-app channel) and the user-visible
  /// message is the same prompt either way.
  /// Polls `/api/signals/pending-suggestions` and fires an auto-timer
  /// suggestion notification for every id we haven't seen. The API stamps
  /// the suggestion when `/suggest-timer` returns a positive match
  /// (daemon side or any client-driven path); the dedupe key is the
  /// suggestion id so a re-poll never double-fires.
  ///
  /// Symmetric with [_pollDrift]: same dedupe namespace pattern, same
  /// best-effort error swallowing. The desktop daemon already fires a
  /// native macOS notification on the same suggestion; this companion
  /// path covers iOS / Android and any desktop without the daemon.
  Future<void> _pollAutoTimer() async {
    try {
      final suggestions = await client.getPendingSuggestions();
      for (final suggestion in suggestions) {
        final id = suggestion['id'] as String?;
        if (id == null || id.isEmpty) continue;
        if (await _dedupe.alreadyNotified('auto-timer', id)) continue;
        final projectId = (suggestion['project_id'] as String?) ?? '';
        final projectName = (suggestion['project_name'] as String?) ?? '';
        // Need both — projectId for the "Start" action button to actually
        // start the timer, projectName for the user-facing copy. Skip
        // (without marking dedupe) if either is missing so a backfilled
        // suggestion can fire later if the API later includes them.
        if (projectId.isEmpty || projectName.isEmpty) continue;
        await notifications.notifyAutoTimerSuggestion(
          projectId: projectId,
          projectName: projectName,
        );
        await _dedupe.markNotified('auto-timer', id);
      }
    } catch (_) {
      // Best-effort — same as the other polls.
    }
  }

  Future<void> _pollDrift() async {
    try {
      final events = await client.getRecentDrift();
      for (final event in events) {
        final id = event['id'] as String?;
        if (id == null || id.isEmpty) continue;
        if (await _dedupe.alreadyNotified('drift', id)) continue;
        final bundleId = (event['bundle_id'] as String?) ?? '';
        final duration = (event['duration_seconds'] as num?)?.toDouble() ?? 0.0;
        await notifications.notifyDriftAlert(
          appLabel: driftAppLabel(bundleId),
          durationSeconds: duration,
        );
        await _dedupe.markNotified('drift', id);
      }
    } catch (_) {
      // Best-effort — same logic as brief / review polls.
    }
  }
}

/// Turns a brief's full body into the ~80-char preview the
/// notification renders. Pure: extracted from NotificationPoller so
/// the whitespace-collapse + truncation rules can be unit-tested
/// without standing up an ApiClient.
///
/// - Empty / null body → null (notifications.notifyBriefAvailable
///   handles null cleanly by rendering a generic title).
/// - All whitespace runs (multiple spaces, tabs, newlines) collapse
///   to a single space — briefs are markdown-ish and look weird in
///   a one-line notification with hard line breaks.
/// - Cap at 80 visible characters and append `…` when truncated.
String? briefPreview(String? body) {
  if (body == null || body.isEmpty) return null;
  final trimmed = body.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (trimmed.isEmpty) return null;
  return trimmed.length > 80 ? '${trimmed.substring(0, 80)}…' : trimmed;
}

/// Map a drift event's bundle id (e.g. "com.twitter.twitter-mac") to a
/// human-readable label for the notification body. Pure: extracted from
/// [NotificationPoller] so the well-known-bundles table can grow with
/// confidence under unit tests.
///
/// Falls back to the last dotted segment titled-cased ("twitter-mac" →
/// "Twitter Mac") when the bundle isn't in the table — still readable,
/// avoids guessing wrong on unknown apps. Empty input returns "an app".
String driftAppLabel(String bundleId) {
  if (bundleId.isEmpty) return 'an app';
  const known = <String, String>{
    'com.twitter.twitter-mac': 'Twitter',
    'com.atebits.tweetie2': 'Twitter',
    'com.spotify.client': 'Spotify',
    'com.hnc.discord': 'Discord',
    'com.reddit.reddit': 'Reddit',
    'com.tinyspeck.slackmacgap': 'Slack',
    'com.facebook.archon.developerID': 'Messenger',
    'com.google.android.youtube': 'YouTube',
    'com.netflix.Netflix': 'Netflix',
    'com.apple.Safari': 'Safari',
    'com.google.Chrome': 'Chrome',
  };
  final lookup = known[bundleId];
  if (lookup != null) return lookup;

  // Fallback: take the last dotted segment, replace dashes with spaces,
  // title-case each word so "twitter-mac" → "Twitter Mac".
  final segments = bundleId.split('.');
  final last = segments.isNotEmpty ? segments.last : bundleId;
  if (last.isEmpty) return bundleId;
  final words = last.split(RegExp(r'[-_]')).where((w) => w.isNotEmpty);
  final titled = words.map((w) =>
      w[0].toUpperCase() + (w.length > 1 ? w.substring(1).toLowerCase() : ''));
  return titled.join(' ');
}
