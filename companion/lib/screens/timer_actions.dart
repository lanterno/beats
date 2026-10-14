import 'package:flutter/material.dart';

import '../services/time_format.dart';
import '../state/timer_controller.dart';

/// Timer actions that report back to the person: every surface that can
/// stop or start the timer goes through these so the confirmation, the
/// Undo and the failure message read the same everywhere.
class TimerActions {
  static Future<void> stop(BuildContext context, TimerController timer) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final stopped = await timer.stop();
      if (stopped == null) return;
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(
        content: Text('${formatDuration(stopped.length)} logged to ${stopped.project.name}'),
        duration: const Duration(seconds: 8),
        action: SnackBarAction(label: 'Undo', onPressed: () => undo(messenger, timer)),
      ));
    } catch (e) {
      _fail(messenger, 'Couldn\'t stop the timer', e);
    }
  }

  static Future<void> undo(ScaffoldMessengerState messenger, TimerController timer) async {
    try {
      await timer.undoStop();
    } catch (e) {
      _fail(messenger, 'Couldn\'t undo', e);
    }
  }

  /// Starts [project], or switches to it when something else is running.
  static Future<void> start(BuildContext context, TimerController timer, Project project, {DateTime? at}) async {
    final messenger = ScaffoldMessenger.of(context);
    final previous = timer.current;
    try {
      await timer.switchTo(project, at: at);
      if (previous != null && previous.id != project.id) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text('Switched from ${previous.name} to ${project.name}')));
      }
    } catch (e) {
      _fail(messenger, 'Couldn\'t start ${project.name}', e);
    }
  }

  static void _fail(ScaffoldMessengerState messenger, String what, Object e) {
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text('$what: $e'), duration: const Duration(seconds: 6)));
  }
}
