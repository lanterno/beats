import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:system_tray/system_tray.dart';
import 'api_client.dart';
import 'mac_ambient.dart';
import 'tray_icon.dart';

/// Decodes a project's hex color string (with or without `#`) into
/// an [r, g, b] triple. Falls back to neutral gray on any parse
/// failure so the tray icon never goes blank — same defensive
/// strategy [trayParseHex] uses on the rendering side. Inverse of
/// [trayHexFromRgb] (in tray_icon.dart) for the round-trip.
List<int> trayHexToRgb(String? hex) {
  if (hex == null || hex.isEmpty) return [122, 122, 122];
  final cleaned = hex.replaceFirst('#', '');
  if (cleaned.length != 6) return [122, 122, 122];
  return [
    int.tryParse(cleaned.substring(0, 2), radix: 16) ?? 122,
    int.tryParse(cleaned.substring(2, 4), radix: 16) ?? 122,
    int.tryParse(cleaned.substring(4, 6), radix: 16) ?? 122,
  ];
}

/// Formats an elapsed duration for the tray's right-side label.
/// `<1h` reads as `MM:SS` (zero-padded — looks like a stopwatch),
/// `≥1h` switches to `Hh MMm` (a stopwatch ticking past 99:59 looks
/// silly in the menu bar). Negative durations clamp to "00:00" so a
/// clock-skew between client and server can't render "-3:00".
String formatTrayElapsed(Duration d) {
  if (d.isNegative) return '00:00';
  final h = d.inHours;
  final m = d.inMinutes.remainder(60);
  final s = d.inSeconds.remainder(60);
  if (h > 0) return '${h}h ${m.toString().padLeft(2, '0')}m';
  return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
}

/// macOS menu bar integration — live timer, quick-start, today's stats.
class TrayService {
  final ApiClient client;
  final VoidCallback onShowWindow;

  final SystemTray _tray = SystemTray();
  final TrayIconRenderer _iconRenderer = TrayIconRenderer();
  Timer? _pollTimer;
  Timer? _tickTimer;
  Timer? _flowTimer;
  // Last 90 min of flow scores (one per ~5-min window the API emits).
  // Drives the menu-bar sparkline. Empty when we haven't fetched yet or
  // when the API call failed — the renderer falls back to a plain dot.
  List<double> _flowScores = const [];

  // State
  bool _running = false;
  String? _projectName;
  String? _projectColorHex;
  DateTime? _startTime;
  List<Map<String, dynamic>> _projects = [];
  // Tracks the last value pushed to the dock badge so we can skip the
  // method-channel hop on every tick (the minute counter only changes
  // every 60 ticks). `null` means "no badge displayed".
  int? _lastBadgeMinutes;

  TrayService({required this.client, required this.onShowWindow});

  Future<void> init() async {
    if (!Platform.isMacOS && !Platform.isWindows && !Platform.isLinux) return;

    final idlePath = await _iconRenderer.idleIcon();
    await _tray.initSystemTray(
      title: '',
      iconPath: idlePath,
      toolTip: 'Pete',
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

    // Refresh the menu-bar sparkline every 5 min. Flow windows are emitted
    // by the daemon at roughly that cadence — polling faster just churns
    // the cache without giving the user new information.
    unawaited(_refreshFlow());
    _flowTimer = Timer.periodic(const Duration(minutes: 5), (_) => _refreshFlow());
  }

  /// Pulls the last 90 min of flow windows and rebuilds the tray icon.
  /// Silent on failure — the existing dot icon stays put.
  Future<void> _refreshFlow() async {
    try {
      final now = DateTime.now().toUtc();
      final start = now.subtract(const Duration(minutes: 90));
      final windows = await client.getFlowWindows(
        start.toIso8601String(),
        now.toIso8601String(),
      );
      final scores = <double>[];
      for (final w in windows) {
        final s = w['score'];
        if (s is num) scores.add(s.toDouble());
      }
      _flowScores = scores;
      await _updateIcon();
    } catch (_) {}
  }

  Future<void> _poll() async {
    try {
      final results = await Future.wait([
        client.getTimerStatus(),
        client.getProjects(),
      ]);
      final status = results[0] as Map<String, dynamic>;
      final projects = results[1] as List<Map<String, dynamic>>;

      final isBeating = status['isBeating'] == true;
      final project = status['project'] as Map<String, dynamic>?;
      final name = project?['name'] as String?;
      final since = status['since'] as String?;

      _projects = projects;
      _running = isBeating;
      _projectName = name;
      _startTime = since != null ? DateTime.tryParse(since) : null;

      // Resolve the running project's color from the projects list so the
      // tray icon can match it. Status payload doesn't carry color today.
      _projectColorHex = null;
      if (isBeating && project != null) {
        final id = project['id'];
        final match = projects.where((p) => p['id'] == id).firstOrNull;
        final hex = match?['color'] as String?;
        if (hex != null) _projectColorHex = hex;
      }

      await _updateIcon();
      await _updateMenu();
      _tick();
    } catch (_) {}
  }

  Future<void> _updateIcon() async {
    final rgb = _running && _projectColorHex != null
        ? trayHexToRgb(_projectColorHex)
        : null;
    // Sparkline takes precedence whenever we have flow data — even idle,
    // a flat-but-recent flow line tells the user something. Fall back to
    // a plain dot when there's no data (fresh launch, API down).
    final path = _flowScores.isNotEmpty
        ? await _iconRenderer.iconForSparkline(_flowScores, rgb)
        : await _iconRenderer.iconForProject(rgb);
    await _tray.setImage(path);
  }

  void _tick() {
    if (_running && _startTime != null) {
      final elapsed = DateTime.now().toUtc().difference(_startTime!);
      final display = formatTrayElapsed(elapsed);
      _tray.setTitle('$display  $_projectName');

      // Mirror the running state into the macOS dock badge. Whole minutes
      // only — pixel-counting seconds in the dock would just create noise.
      // Skip the channel hop when the value hasn't changed.
      final mins = elapsed.inMinutes;
      if (mins != _lastBadgeMinutes) {
        MacAmbient.setDockBadge('$mins');
        _lastBadgeMinutes = mins;
      }
    } else {
      _tray.setTitle('');
      if (_lastBadgeMinutes != null) {
        MacAmbient.setDockBadge(null);
        _lastBadgeMinutes = null;
      }
    }
  }

  Future<void> _updateMenu() async {
    final menu = Menu();
    final items = <MenuItemBase>[];

    if (_running && _projectName != null) {
      // ── Running state ──
      final elapsed = _startTime != null
          ? formatTrayElapsed(DateTime.now().toUtc().difference(_startTime!))
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
      final match = _projects.where((p) => p['id'] == projectId).firstOrNull;
      _projectColorHex = match?['color'] as String?;
      _startTime = DateTime.now().toUtc();
      await _updateIcon();
      await _updateMenu();
      _tick();
    } catch (_) {}
  }

  Future<void> _stopTimer() async {
    try {
      await client.stopTimer();
      _running = false;
      _projectName = null;
      _projectColorHex = null;
      _startTime = null;
      await _updateIcon();
      await _updateMenu();
      _tray.setTitle('');
    } catch (_) {}
  }

  void dispose() {
    _pollTimer?.cancel();
    _tickTimer?.cancel();
    _flowTimer?.cancel();
    _tray.destroy();
  }
}
