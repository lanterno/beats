import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:system_tray/system_tray.dart';
import 'api_client.dart';

/// macOS menu bar integration — live timer, quick-start, today's stats.
class TrayService {
  final ApiClient client;
  final VoidCallback onShowWindow;

  final SystemTray _tray = SystemTray();
  Timer? _pollTimer;
  Timer? _tickTimer;

  // State
  bool _running = false;
  String? _projectName;
  DateTime? _startTime;
  List<Map<String, dynamic>> _projects = [];

  TrayService({required this.client, required this.onShowWindow});

  Future<void> init() async {
    if (!Platform.isMacOS && !Platform.isWindows && !Platform.isLinux) return;

    await _tray.initSystemTray(
      title: '',
      iconPath: '',
      toolTip: 'Beats Companion',
    );

    _tray.registerSystemTrayEventHandler((eventName) {
      if (eventName == kSystemTrayEventClick) {
        _tray.popUpContextMenu();
      } else if (eventName == kSystemTrayEventRightClick) {
        _tray.popUpContextMenu();
      }
    });

    // Initial fetch
    await _poll();

    // Poll API every 15s for state changes
    _pollTimer = Timer.periodic(const Duration(seconds: 15), (_) => _poll());

    // Tick every second to update elapsed time in menu bar
    _tickTimer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
  }

  Future<void> _poll() async {
    try {
      final status = await client.getTimerStatus();
      final projects = await client.getProjects();

      final isBeating = status['isBeating'] == true;
      final project = status['project'] as Map<String, dynamic>?;
      final name = project?['name'] as String?;
      final since = status['since'] as String?;

      _projects = projects;
      _running = isBeating;
      _projectName = name;
      _startTime = since != null ? DateTime.tryParse(since) : null;

      // Compute today's total from the so_far field or estimate
      // For now, show current session duration as "today"
      await _updateMenu();
      _tick();
    } catch (_) {}
  }

  void _tick() {
    if (_running && _startTime != null) {
      final elapsed = DateTime.now().toUtc().difference(_startTime!);
      final display = _formatElapsed(elapsed);
      _tray.setTitle('$display  $_projectName');
    } else {
      _tray.setTitle('');
    }
  }

  Future<void> _updateMenu() async {
    final menu = Menu();
    final items = <MenuItemBase>[];

    if (_running && _projectName != null) {
      // ── Running state ──
      final elapsed = _startTime != null
          ? _formatElapsed(DateTime.now().toUtc().difference(_startTime!))
          : '—';
      items.addAll([
        MenuItemLabel(label: '● $_projectName — $elapsed', enabled: false),
        MenuSeparator(),
        MenuItemLabel(label: '■  Stop Timer', onClicked: (_) => _stopTimer()),
        MenuSeparator(),
      ]);
    } else {
      // ── Idle state ──
      items.add(MenuItemLabel(label: 'No timer running', enabled: false));
      items.add(MenuSeparator());

      // Quick-start submenu
      if (_projects.isNotEmpty) {
        final projectItems = <MenuItemBase>[];
        for (final p in _projects.take(12)) {
          final name = p['name'] as String? ?? 'Unnamed';
          final id = p['id'] as String? ?? '';
          projectItems.add(
            MenuItemLabel(
              label: name,
              onClicked: (_) => _startTimer(id, name),
            ),
          );
        }
        final startMenu = SubMenu(label: '▶  Start Timer', children: projectItems);
        items.add(startMenu);
        items.add(MenuSeparator());
      }
    }

    // Always show Open + Quit
    items.add(MenuItemLabel(label: 'Open Beats', onClicked: (_) => onShowWindow()));
    items.add(MenuSeparator());
    items.add(MenuItemLabel(label: 'Quit', onClicked: (_) => exit(0)));

    await menu.buildFrom(items);
    await _tray.setContextMenu(menu);
  }

  Future<void> _startTimer(String projectId, String projectName) async {
    try {
      await client.startTimer(projectId);
      _running = true;
      _projectName = projectName;
      _startTime = DateTime.now().toUtc();
      await _updateMenu();
      _tick();
    } catch (_) {}
  }

  Future<void> _stopTimer() async {
    try {
      await client.stopTimer();
      _running = false;
      _projectName = null;
      _startTime = null;
      await _updateMenu();
      _tray.setTitle('');
    } catch (_) {}
  }

  String _formatElapsed(Duration d) {
    final h = d.inHours;
    final m = d.inMinutes.remainder(60);
    final s = d.inSeconds.remainder(60);
    if (h > 0) return '${h}h ${m.toString().padLeft(2, '0')}m';
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  void dispose() {
    _pollTimer?.cancel();
    _tickTimer?.cancel();
    _tray.destroy();
  }
}
