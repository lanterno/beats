import 'dart:async';

import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
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

  NotificationPoller({
    required this.client,
    required this.notifications,
    this.interval = const Duration(minutes: 5),
  });

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
      if (await _alreadyNotified('brief', id)) return;
      // Use the first ~80 chars of the brief body as a preview so the
      // notification reads like a real prompt, not just "you have a brief".
      final body = brief['body'] as String?;
      String? preview;
      if (body != null && body.isNotEmpty) {
        final trimmed = body.replaceAll(RegExp(r'\s+'), ' ').trim();
        preview = trimmed.length > 80 ? '${trimmed.substring(0, 80)}…' : trimmed;
      }
      await notifications.notifyBriefAvailable(preview: preview);
      await _markNotified('brief', id);
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
      if (await _alreadyNotified('review', date)) return;
      await notifications.notifyReviewAvailable();
      await _markNotified('review', date);
    } catch (_) {
      // Same as above — best-effort.
    }
  }

  static Future<bool> _alreadyNotified(String kind, String id) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('beats_notified_$kind') == id;
  }

  static Future<void> _markNotified(String kind, String id) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('beats_notified_$kind', id);
  }
}
