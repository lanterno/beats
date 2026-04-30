import 'dart:async';
import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest_all.dart' as tz_db;
import 'package:timezone/timezone.dart' as tz;

/// Singleton wrapper around `flutter_local_notifications` that handles init,
/// permission, scheduling, and tap routing.
///
/// **Free-tier path**: this is purely local notifications — no APNs/FCM, no
/// server-side push. Two delivery mechanisms:
///
/// 1. `scheduleEodMoodPrompt` schedules a daily repeating notification at a
///    user-chosen time. This fires even when the app isn't running.
/// 2. `notifyBriefAvailable`, `notifyReviewAvailable`, etc. fire instantly.
///    The companion's [NotificationPoller] checks the API on a 5-minute
///    foreground loop and calls these when new content arrives — so they
///    only fire while the app is alive.
class NotificationsService {
  NotificationsService._();
  static final NotificationsService instance = NotificationsService._();

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  /// Notification IDs are stable so re-scheduling the EOD prompt overwrites
  /// the previous schedule rather than stacking duplicates.
  static const int _idEod = 100;
  static const int _idBrief = 101;
  static const int _idReview = 102;
  static const int _idAutoTimer = 103;

  /// Channel identifiers (Android only — iOS uses a single global channel).
  static const String _channelId = 'beats.coach';
  static const String _channelName = 'Beats Coach';
  static const String _channelDesc = 'Brief, review, mood, and auto-timer prompts';

  /// Streams every tap on a Beats notification. Subscribers get the optional
  /// payload so they can route to the right tab. Returns null payload on
  /// platforms that don't carry one.
  final StreamController<String?> _taps = StreamController<String?>.broadcast();
  Stream<String?> get taps => _taps.stream;

  Future<void> init() async {
    if (_ready) return;

    // Initialize the timezone database so zonedSchedule has names.
    tz_db.initializeTimeZones();
    try {
      final localName = await FlutterTimezone.getLocalTimezone();
      tz.setLocalLocation(tz.getLocation(localName));
    } catch (_) {
      // Fall back to UTC if the platform can't tell us the local TZ —
      // worst case the EOD prompt fires at the wrong hour for one day
      // until the user resets it.
    }

    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const darwinInit = DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
    );
    const linuxInit = LinuxInitializationSettings(defaultActionName: 'Open');

    const settings = InitializationSettings(
      android: androidInit,
      iOS: darwinInit,
      macOS: darwinInit,
      linux: linuxInit,
    );

    await _plugin.initialize(
      settings,
      onDidReceiveNotificationResponse: (response) {
        _taps.add(response.payload);
      },
    );

    _ready = true;
  }

  /// Triggers the OS permission prompt on platforms where notifications are
  /// opt-in. Safe to call repeatedly; the OS only shows the dialog once.
  /// Returns true if the user has granted permission.
  Future<bool> requestPermissions() async {
    if (!_ready) await init();

    if (Platform.isIOS || Platform.isMacOS) {
      final granted = await _plugin
              .resolvePlatformSpecificImplementation<
                  IOSFlutterLocalNotificationsPlugin>()
              ?.requestPermissions(alert: true, badge: true, sound: true) ??
          await _plugin
              .resolvePlatformSpecificImplementation<
                  MacOSFlutterLocalNotificationsPlugin>()
              ?.requestPermissions(alert: true, badge: true, sound: true);
      return granted ?? false;
    }

    if (Platform.isAndroid) {
      final granted = await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
      return granted ?? false;
    }

    return true; // Linux / Windows have no opt-in dialog
  }

  NotificationDetails _details({String? subtitle}) => NotificationDetails(
        android: const AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDesc,
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
        ),
        iOS: DarwinNotificationDetails(subtitle: subtitle),
        macOS: DarwinNotificationDetails(subtitle: subtitle),
        linux: const LinuxNotificationDetails(),
      );

  /// Cancels the existing EOD schedule (if any) and reschedules a daily
  /// repeating notification at [time]. The notification fires even when the
  /// app isn't running.
  Future<void> scheduleEodMoodPrompt({
    required int hour,
    required int minute,
  }) async {
    if (!_ready) await init();
    await _plugin.cancel(_idEod);

    final now = tz.TZDateTime.now(tz.local);
    var when = tz.TZDateTime(tz.local, now.year, now.month, now.day, hour, minute);
    if (!when.isAfter(now)) {
      when = when.add(const Duration(days: 1));
    }

    await _plugin.zonedSchedule(
      _idEod,
      'How was today?',
      'A minute of reflection — log your mood and what went well.',
      when,
      _details(subtitle: 'Beats'),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      matchDateTimeComponents: DateTimeComponents.time, // repeat daily at HH:MM
      payload: 'eod-mood',
    );
  }

  Future<void> cancelEodMoodPrompt() async {
    if (!_ready) await init();
    await _plugin.cancel(_idEod);
  }

  /// One-shot "your morning brief is ready" prompt. Caller is responsible
  /// for de-duplication (only call once per brief).
  Future<void> notifyBriefAvailable({String? preview}) async {
    if (!_ready) await init();
    await _plugin.show(
      _idBrief,
      'Your morning brief is ready',
      preview ?? 'Tap to read what the coach has for you today.',
      _details(subtitle: 'Beats coach'),
      payload: 'brief',
    );
  }

  Future<void> notifyReviewAvailable() async {
    if (!_ready) await init();
    await _plugin.show(
      _idReview,
      'Time to review the day',
      'A few questions to help close the loop.',
      _details(subtitle: 'Beats coach'),
      payload: 'review',
    );
  }

  /// Fired when the daemon detects high flow without a running timer and
  /// suggests starting one for [projectName].
  Future<void> notifyAutoTimerSuggestion(String projectName) async {
    if (!_ready) await init();
    await _plugin.show(
      _idAutoTimer,
      'Start tracking?',
      'You\'ve been deep in $projectName for a while.',
      _details(subtitle: 'Beats'),
      payload: 'auto-timer:$projectName',
    );
  }

  Future<void> dispose() async {
    await _taps.close();
  }
}
