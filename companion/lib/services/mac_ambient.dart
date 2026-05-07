import 'dart:io';
import 'package:flutter/services.dart';

/// macOS-only ambient surfaces. Today: just the dock badge.
///
/// On non-macOS platforms every method is a silent no-op so callers can
/// invoke them unconditionally. The native side lives in
/// `macos/Runner/PeteMacOS.swift` and is registered from
/// `MainFlutterWindow.swift`. We pin the channel name here to the same
/// string the Swift constant uses; if you rename one, rename both.
class MacAmbient {
  static const _channel = MethodChannel('pete/macos');

  /// Sets the live label on Pete's dock icon. `null` or empty clears it.
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
}
