import 'dart:io';

import 'package:flutter/services.dart';

/// The main window's side of the macOS menu bar item
/// (`macos/Runner/StatusItemController.swift`): sets what the item shows,
/// tells an open popover the timer changed, hears the popover ask for the
/// window, and registers, records and answers the global shortcuts
/// (services/shortcuts.dart). Every method is a no-op off macOS, where
/// TrayService uses the tray_manager plugin instead.
class StatusMenu {
  static const _channel = MethodChannel('companion/menubar');

  /// [template] has macOS draw the image in the menu bar's own colour, from
  /// its alpha alone, as it does every system icon; an image in a fixed
  /// colour can vanish against the wallpaper a translucent menu bar shows.
  static Future<void> update({
    required bool visible,
    String title = '',
    String? imagePath,
    bool template = false,
    String? tooltip,
  }) async {
    if (!Platform.isMacOS) return;
    try {
      await _channel.invokeMethod('status.update', {
        'visible': visible,
        'title': title,
        'imagePath': ?imagePath,
        'template': template,
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
    _show = show;
    _refresh = refresh;
    _listen();
  }

  /// [handle] gets the global shortcuts the window acts on (`startLast`,
  /// `stop`) and answers whether there was anything to do; the Mac beeps
  /// when there was not. Set at startup, paired or not.
  static void onShortcut(Future<bool> Function(String action) handle) {
    _shortcut = handle;
    _listen();
  }

  /// Registers [bindings] (ShortcutBindings.toNative) and returns the names of the
  /// actions macOS refused, another app holding their combination.
  static Future<List<String>> setShortcuts(Map<String, Object?> bindings) async {
    if (!Platform.isMacOS) return const [];
    try {
      final refused = await _channel.invokeMethod<List<Object?>>('shortcuts.set', {'bindings': bindings});
      return refused?.whereType<String>().toList() ?? const [];
    } catch (_) {
      return const [];
    }
  }

  /// The next key pressed in the app, every shortcut off meanwhile, as
  /// `{keyCode, modifiers, key}`; null when Esc or [cancelRecording] ends it.
  static Future<Map<Object?, Object?>?> recordShortcut() async {
    if (!Platform.isMacOS) return null;
    try {
      return await _channel.invokeMethod<Map<Object?, Object?>>('shortcuts.record');
    } catch (_) {
      return null;
    }
  }

  static Future<void> cancelRecording() async {
    if (!Platform.isMacOS) return;
    try {
      await _channel.invokeMethod('shortcuts.cancelRecord');
    } catch (_) {}
  }

  static void Function(String? section, String? route)? _show;
  static void Function()? _refresh;
  static Future<bool> Function(String action)? _shortcut;
  static bool _listening = false;

  static void _listen() {
    if (!Platform.isMacOS || _listening) return;
    _listening = true;
    _channel.setMethodCallHandler((call) async {
      final args = (call.arguments as Map?)?.cast<String, Object?>() ?? const {};
      switch (call.method) {
        case 'window.show':
          _show?.call(args['section'] as String?, args['route'] as String?);
        case 'timer.refresh':
          _refresh?.call();
        case 'shortcut.pressed':
          final handle = _shortcut;
          return handle == null ? false : await handle(args['action'] as String? ?? '');
      }
      return null;
    });
  }
}
