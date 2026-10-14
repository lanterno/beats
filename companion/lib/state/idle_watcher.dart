import 'dart:async';

import 'package:flutter/foundation.dart';

import '../services/idle_tracker.dart';
import '../services/mac_ambient.dart';
import '../services/notifications.dart';
import '../services/time_format.dart';
import 'prefs.dart';
import 'timer_controller.dart';

/// A stretch away the running timer counted, waiting for an answer.
class AwayAsk {
  final AwayPeriod period;
  final Project project;

  /// The session's start when the stretch was seen; if the timer has been
  /// stopped or switched since, the question no longer applies.
  final DateTime since;
  const AwayAsk(this.period, this.project, this.since);
}

/// Asks about time away (Settings › Notifications, off by default): while a
/// timer runs, reads the Mac's idle time every 20 seconds, and when input
/// comes back after ten minutes or more without any, asks — a notification
/// and a banner on Today — whether to keep that time or take it off.
class IdleWatcher extends ChangeNotifier {
  final TimerController timer;
  final IdleTracker _tracker;
  final Future<Duration?> Function() _readIdle;
  final Future<void> Function(AwayAsk) _notify;

  IdleWatcher(
    this.timer, {
    IdleTracker? tracker,
    Future<Duration?> Function()? readIdle,
    Future<void> Function(AwayAsk)? notify,
  })  : _tracker = tracker ?? IdleTracker(),
        _readIdle = readIdle ?? MacAmbient.idleTime,
        _notify = notify ?? _notifyByNotification;

  static Future<void> _notifyByNotification(AwayAsk ask) =>
      NotificationsService.instance.notifyAwayWhileRunning(
        projectName: ask.project.name,
        from: formatTimeOfDay(ask.period.from),
        to: formatTimeOfDay(ask.period.to),
        minutes: ask.period.length.inMinutes,
      );

  AwayAsk? pending;
  Timer? _poll;

  void start() {
    _poll = Timer.periodic(const Duration(seconds: 20), (_) => check());
  }

  /// One reading. Public so a test can drive it.
  Future<void> check({DateTime? now}) async {
    final prefs = await Prefs.load();
    if (!prefs.askingOnIdle || !timer.running) {
      _tracker.reset();
      return;
    }
    final idle = await _readIdle();
    if (idle == null) return;
    final at = now ?? DateTime.now();
    final period = _tracker.sample(at, idle);
    final since = timer.since;
    final project = timer.current;
    // Only a stretch the running session fully covers is a question.
    if (period == null || since == null || project == null || period.from.isBefore(since)) return;
    final ask = AwayAsk(period, project, since);
    pending = ask;
    notifyListeners();
    await _notify(ask);
  }

  /// Cuts the stretch out: the session ends where input stopped and a new
  /// one starts where it came back. Does nothing if the timer has moved on.
  Future<void> takeOff() async {
    final ask = pending;
    if (ask == null) return;
    pending = null;
    notifyListeners();
    if (timer.current?.id != ask.project.id || timer.since != ask.since) return;
    await timer.stop(at: ask.period.from);
    await timer.startProject(ask.project, at: ask.period.to);
  }

  void keep() {
    if (pending == null) return;
    pending = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }
}
