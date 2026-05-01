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
      await Future.wait([_pollBrief(), _pollReview()]);
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
