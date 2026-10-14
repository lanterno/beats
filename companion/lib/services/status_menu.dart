import 'dart:io';

import 'package:flutter/services.dart';

/// The main window's side of the macOS menu bar item
/// (`macos/Runner/StatusItemController.swift`): sets what the item shows,
/// tells an open popover the timer changed, and hears the popover ask for
/// the window. Every method is a no-op off macOS, where TrayService uses the
/// system_tray plugin instead.
class StatusMenu {
  static const _channel = MethodChannel('companion/menubar');

  static Future<void> update({
    required bool visible,
    String title = '',
    String? imagePath,
    String? tooltip,
  }) async {
    if (!Platform.isMacOS) return;
    try {
      await _channel.invokeMethod('status.update', {
        'visible': visible,
        'title': title,
        'imagePath': ?imagePath,
        'tooltip': ?tooltip,
      });
    } catch (_) {}
  }

  static Future<void> timerChanged() async {
    if (!Platform.isMacOS) return;
    try {
      await _channel.invokeMethod('timer.changed');
    } catch (_) {}
  }

  /// [show] gets the place (`today`, `flow`, `coach`, `body`) or route
  /// (`settings`, `focus`) the popover asked for, either may be null;
  /// [refresh] runs when the popover changed the timer.
  static void listen({
    required void Function(String? section, String? route) show,
    required void Function() refresh,
  }) {
    if (!Platform.isMacOS) return;
    _channel.setMethodCallHandler((call) async {
      final args = (call.arguments as Map?)?.cast<String, Object?>() ?? const {};
      switch (call.method) {
        case 'window.show':
          show(args['section'] as String?, args['route'] as String?);
        case 'timer.refresh':
          refresh();
      }
    });
  }
}
