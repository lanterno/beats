import 'dart:io';
import 'package:flutter/services.dart';

/// macOS-only ambient surfaces: the Dock badge and icon, opening at login,
/// and idle time.
///
/// On non-macOS platforms every method is a silent no-op so callers can
/// invoke them unconditionally. The native side lives in
/// `macos/Runner/MacAmbientBridge.swift` and is registered from
/// `MainFlutterWindow.swift`. We pin the channel name here to the same
/// string the Swift constant uses; if you rename one, rename both.
class MacAmbient {
  static const _channel = MethodChannel('companion/macos');

  /// Sets the live label on the app's dock icon. `null` or empty clears it.
  /// We send `"32"` while a 32-minute timer is running and `null` when
  /// idle — the badge reads like a wristwatch in peripheral vision.
  static Future<void> setDockBadge(String? label) async {
    if (!Platform.isMacOS) return;
    try {
      await _channel.invokeMethod('dock.setBadge', {'label': label});
    } catch (_) {
      // Method-channel failures shouldn't take the timer down. The dock
      // is decoration; the underlying timer state is still authoritative.
    }
  }

  /// Whether LifePete opens at login, or null where macOS can't say
  /// (before macOS 13, or off a Mac).
  static Future<bool?> openAtLogin() async {
    if (!Platform.isMacOS) return null;
    try {
      return await _channel.invokeMethod<bool>('login.isEnabled');
    } catch (_) {
      return null;
    }
  }

  /// Registers or removes LifePete as a login item. Returns the state
  /// macOS reports afterwards; throws with macOS's reason on failure.
  static Future<bool> setOpenAtLogin(bool enabled) async {
    final ok = await _channel.invokeMethod<bool>('login.setEnabled', {'enabled': enabled});
    return ok ?? false;
  }

  /// Shows or hides the Dock icon. Hidden, LifePete lives in the menu bar.
  static Future<void> setDockVisible(bool visible) async {
    if (!Platform.isMacOS) return;
    try {
      await _channel.invokeMethod('dock.setVisible', {'visible': visible});
    } catch (_) {}
  }

  /// How long since the last keyboard or mouse input, or null off a Mac
  /// or when macOS doesn't say.
  static Future<Duration?> idleTime() async {
    if (!Platform.isMacOS) return null;
    try {
      final seconds = await _channel.invokeMethod<double>('idle.seconds');
      return seconds == null ? null : Duration(milliseconds: (seconds * 1000).round());
    } catch (_) {
      return null;
    }
  }
}
