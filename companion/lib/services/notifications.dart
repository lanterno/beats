import 'dart:async';
import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest_all.dart' as tz_db;
import 'package:timezone/timezone.dart' as tz;

/// One tap event from the notification surface. [actionId] is null when
/// the user tapped the notification body itself (rather than a specific
/// action button); routers switch on it to decide between "open the
/// relevant tab" and "execute the action button's effect".
class NotificationTap {
  final String? payload;
  final String? actionId;

  const NotificationTap({this.payload, this.actionId});
}

/// Identifier for the auto-timer "Start" action button. Stable string —
/// used both for registration (Android `AndroidNotificationAction.id`,
/// iOS `DarwinNotificationAction.identifier`) and for routing in the
/// tap consumer.
const String kStartAutoTimerActionId = 'start-auto-timer';

/// iOS `DarwinNotificationCategory` identifier carrying the Start action.
/// `notifyAutoTimerSuggestion` sets this on the iOS payload so the user
/// long-presses (or 3D touches) into the action; on Android the same
/// action is attached per-message via `actions`.
const String _autoTimerCategoryId = 'beats.auto-timer';

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
  static const int _idDrift = 104;

  /// Channel identifiers (Android only — iOS uses a single global channel).
  static const String _channelId = 'beats.coach';
  static const String _channelName = 'Beats Coach';
  static const String _channelDesc = 'Brief, review, mood, and auto-timer prompts';

  /// Streams every tap on a Beats notification. Subscribers get the
  /// payload + the optional actionId (null when the user tapped the body
  /// rather than an action button). Routers switch on actionId to decide
  /// "open the right tab" vs "execute the button's effect".
  final StreamController<NotificationTap> _taps =
      StreamController<NotificationTap>.broadcast();
  Stream<NotificationTap> get taps => _taps.stream;

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
    // Register the auto-timer action category on iOS / macOS up-front so
    // every notification with `categoryIdentifier: _autoTimerCategoryId`
    // shows the "Start" button when the user expands it.
    final darwinInit = DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
      notificationCategories: [
        DarwinNotificationCategory(
          _autoTimerCategoryId,
          actions: [
            DarwinNotificationAction.plain(
              kStartAutoTimerActionId,
              'Start',
              options: const {DarwinNotificationActionOption.foreground},
            ),
          ],
        ),
      ],
    );
    const linuxInit = LinuxInitializationSettings(defaultActionName: 'Open');

    final settings = InitializationSettings(
      android: androidInit,
      iOS: darwinInit,
      macOS: darwinInit,
      linux: linuxInit,
    );

    await _plugin.initialize(
      settings,
      onDidReceiveNotificationResponse: (response) {
        _taps.add(NotificationTap(
          payload: response.payload,
          actionId: response.actionId,
        ));
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

  NotificationDetails _details({
    String? subtitle,
    List<AndroidNotificationAction>? androidActions,
    String? darwinCategoryIdentifier,
  }) =>
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDesc,
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
          actions: androidActions,
        ),
        iOS: DarwinNotificationDetails(
          subtitle: subtitle,
          categoryIdentifier: darwinCategoryIdentifier,
        ),
        macOS: DarwinNotificationDetails(
          subtitle: subtitle,
          categoryIdentifier: darwinCategoryIdentifier,
        ),
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

  /// Fired when the API surfaces a pending auto-timer suggestion. The
  /// notification carries a "Start" action button that, when tapped, fires
  /// a [NotificationTap] with `actionId == kStartAutoTimerActionId` —
  /// the main app's tap router calls `client.startTimer(projectId)`
  /// without ever opening a screen.
  ///
  /// Payload encoding: `auto-timer:<projectId>|<projectName>` so the tap
  /// router can both POST `/api/timer/start` (needs the id) and write a
  /// confirmation toast (needs the human-readable name). Encoded as a
  /// single string because flutter_local_notifications only carries one
  /// payload string per notification. See [parseAutoTimerPayload].
  Future<void> notifyAutoTimerSuggestion({
    required String projectId,
    required String projectName,
  }) async {
    if (!_ready) await init();
    await _plugin.show(
      _idAutoTimer,
      'Start tracking?',
      'You\'ve been deep in $projectName for a while.',
      _details(
        subtitle: 'Beats',
        androidActions: const [
          AndroidNotificationAction(
            kStartAutoTimerActionId,
            'Start',
            showsUserInterface: false,
            cancelNotification: true,
          ),
        ],
        darwinCategoryIdentifier: _autoTimerCategoryId,
      ),
      payload: 'auto-timer:$projectId|$projectName',
    );
  }

  /// Fired when the daemon's shield records a drift event (a stretch of
  /// time on a known distraction bundle). [appLabel] is a human-readable
  /// label derived from the bundle id (see [driftAppLabel] in
  /// `notification_poller.dart`); [durationSeconds] is the length of the
  /// drift window so the user understands the magnitude.
  Future<void> notifyDriftAlert({
    required String appLabel,
    required double durationSeconds,
  }) async {
    if (!_ready) await init();
    final mins = (durationSeconds / 60).round();
    final body = mins >= 1
        ? 'You\'ve been on $appLabel for ${mins}m while a timer is running.'
        : 'You\'ve drifted to $appLabel while a timer is running.';
    await _plugin.show(
      _idDrift,
      'Drift detected',
      body,
      _details(subtitle: 'Beats'),
      payload: 'drift:$appLabel',
    );
  }

  Future<void> dispose() async {
    await _taps.close();
  }
}

/// Parsed `auto-timer` payload. `null` from [parseAutoTimerPayload] means
/// the payload didn't match the expected `auto-timer:<id>|<name>` shape —
/// the router should ignore it rather than trying to start a timer with
/// missing data.
class AutoTimerPayload {
  final String projectId;
  final String projectName;
  const AutoTimerPayload({required this.projectId, required this.projectName});
}

/// Decode the payload encoded by [NotificationsService.notifyAutoTimerSuggestion].
/// Pure: extracted so the encoding contract can be locked in by unit tests
/// without booting the notifications plugin.
///
/// Returns null when the payload is null, doesn't start with `auto-timer:`,
/// or carries an empty project id. The project name is allowed to be empty
/// (the toast just falls back to a generic confirmation in that case).
AutoTimerPayload? parseAutoTimerPayload(String? payload) {
  if (payload == null) return null;
  const prefix = 'auto-timer:';
  if (!payload.startsWith(prefix)) return null;
  final rest = payload.substring(prefix.length);
  // Project id is everything before the first '|'; everything after is the
  // human-readable name (which may itself contain '|' characters — split
  // on the first separator only so a stray pipe in the name doesn't
  // truncate it).
  final sep = rest.indexOf('|');
  final projectId = sep < 0 ? rest : rest.substring(0, sep);
  if (projectId.isEmpty) return null;
  final projectName = sep < 0 ? '' : rest.substring(sep + 1);
  return AutoTimerPayload(projectId: projectId, projectName: projectName);
}
