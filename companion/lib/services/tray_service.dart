import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:system_tray/system_tray.dart';
import 'api_client.dart';

/// Manages the macOS menu bar (system tray) icon and menu.
/// Shows timer state and allows quick start/stop.
class TrayService {
  final ApiClient client;
  final VoidCallback onShowWindow;

  final SystemTray _tray = SystemTray();
  Timer? _pollTimer;
  bool _running = false;
  String? _projectName;

  TrayService({required this.client, required this.onShowWindow});

  Future<void> init() async {
    if (!Platform.isMacOS && !Platform.isWindows && !Platform.isLinux) return;

    await _tray.initSystemTray(
      title: '',
      iconPath: '', // empty = default app icon
      toolTip: 'Beats Companion',
    );

    _tray.registerSystemTrayEventHandler((eventName) {
      if (eventName == kSystemTrayEventClick) {
        onShowWindow();
      } else if (eventName == kSystemTrayEventRightClick) {
        _tray.popUpContextMenu();
      }
    });

    await _updateMenu();
    _pollTimer = Timer.periodic(const Duration(seconds: 10), (_) => _poll());
    _poll();
  }

  Future<void> _poll() async {
    try {
      final status = await client.getTimerStatus();
      final isBeating = status['isBeating'] == true;
      final project = status['project'] as Map<String, dynamic>?;
      final name = project?['name'] as String?;

      if (isBeating != _running || name != _projectName) {
        _running = isBeating;
        _projectName = name;
        await _updateMenu();
        await _tray.setTitle(_running ? '${_projectName ?? "Working"}' : '');
      }
    } catch (_) {}
  }

  Future<void> _updateMenu() async {
    final menu = Menu();

    if (_running && _projectName != null) {
      await menu.buildFrom([
        MenuItemLabel(label: '● $_projectName', enabled: false),
        MenuSeparator(),
        MenuItemLabel(label: 'Stop Timer', onClicked: (_) async {
          try {
            await client.stopTimer();
            _running = false;
            _projectName = null;
            await _updateMenu();
            await _tray.setTitle('');
          } catch (_) {}
        }),
        MenuSeparator(),
        MenuItemLabel(label: 'Open Beats', onClicked: (_) => onShowWindow()),
      ]);
    } else {
      await menu.buildFrom([
        MenuItemLabel(label: 'No timer running', enabled: false),
        MenuSeparator(),
        MenuItemLabel(label: 'Open Beats', onClicked: (_) => onShowWindow()),
      ]);
    }

    await _tray.setContextMenu(menu);
  }

  void dispose() {
    _pollTimer?.cancel();
    _tray.destroy();
  }
}
