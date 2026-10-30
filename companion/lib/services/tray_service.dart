import 'dart:async';
import 'dart:io';
import 'package:material_ui/material_ui.dart';
import 'package:tray_manager/tray_manager.dart' as tray;
import '../brand.dart';
import '../state/prefs.dart';
import '../state/timer_controller.dart';
import 'api_client.dart';
import 'mac_ambient.dart';
import 'status_menu.dart';
import 'time_format.dart';
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

/// Extracts the flow-score series for the menu-bar sparkline from the raw
/// `/api/signals/flow-windows` response. Reads each window's `flow_score`
/// field — the key the API actually emits (see FlowScreen + signals.py),
/// NOT `score` — coerces num→double, skips windows with a missing or
/// non-numeric score, and clamps to [0,1] so one malformed window can't
/// blow out the sparkline's y-range. Extracted from [TrayService._refreshFlow]
/// so the parsing (and the field name) is unit-tested.
List<double> flowScoresFromWindows(List<Map<String, dynamic>> windows) {
  final scores = <double>[];
  for (final w in windows) {
    final s = w['flow_score'];
    if (s is num) scores.add(s.clamp(0.0, 1.0).toDouble());
  }
  return scores;
}

/// The macOS dock-badge label for the current timer state: whole elapsed
/// minutes while running, or `null` when idle (which clears the badge).
/// Negative elapsed (client/server clock skew) clamps to "0" so the badge
/// never renders "-1". Extracted from [TrayService._tick] so the badge
/// transitions are unit-testable without a desktop binding.
String? dockBadgeForElapsed(Duration? elapsed, {required bool running}) {
  if (!running || elapsed == null) return null;
  final mins = elapsed.isNegative ? 0 : elapsed.inMinutes;
  return '$mins';
}

/// What the menu bar item reads while [project] has run for [elapsed]:
/// "1:24 Northwind", "1:24" or nothing, per [shows]; nothing when idle.
String menuBarTitle(MenuBarShows shows, {String? project, Duration? elapsed}) {
  if (project == null || elapsed == null) return '';
  return switch (shows) {
    MenuBarShows.timeAndProject => '${formatShortClock(elapsed)} $project',
    MenuBarShows.time => formatShortClock(elapsed),
    MenuBarShows.icon => '',
  };
}

/// The menu bar item: the running timer's time and project, an icon that
/// carries the project's colour and the last 90 minutes of flow, and the
/// Dock badge. It follows the window's [TimerController] rather than
/// polling on its own, so a start anywhere shows at once.
///
/// On macOS the item is native (StatusItemController.swift, via
/// [StatusMenu]) and a click opens the popover; elsewhere it is the
/// tray_manager plugin with a menu to start and stop. tray_manager replaced
/// system_tray (#395): same four calls — icon, title, tooltip, menu — but
/// maintained, and its native core is built by Dart's build hooks, so the
/// macOS build has no tray pod or Swift package to host at all.
class TrayService {
  final ApiClient client;
  final TimerController timer;
  final VoidCallback onShowWindow;

  final bool _native = Platform.isMacOS;
  tray.TrayIcon? _tray;
  // The menu in the tray and its items, held on purpose: a wrapper that is
  // garbage-collected releases its native handle, which would strip the
  // click listeners (and the icon, were _tray not a field) mid-session.
  // Never read — being referenced is their whole job.
  // ignore: unused_field
  tray.Menu? _menu;
  // ignore: unused_field
  List<tray.MenuItem> _menuItems = const [];
  final TrayIconRenderer _iconRenderer = TrayIconRenderer();
  Prefs? _prefs;
  Timer? _flowTimer;
  // Last 90 min of flow scores (one per window the API emits). Drives the
  // menu-bar sparkline. Empty when we haven't fetched yet or when the API
  // call failed — the renderer falls back to a plain dot.
  List<double> _flowScores = const [];
  String? _iconPath;
  // Nothing running: the icon is drawn in the menu bar's own colour, since
  // the idle grey all but vanishes on a dark or busy menu bar. A running
  // project keeps its colour.
  bool get _iconTemplate => timer.current == null;
  String _timerKey = '';
  String? _lastTitle;
  // Tracks the last label pushed to the dock badge so we can skip the
  // method-channel hop on every tick (the minute counter only changes
  // every 60 ticks). `null` means "no badge displayed".
  String? _lastBadge;

  TrayService({required this.client, required this.timer, required this.onShowWindow});

  Future<void> init() async {
    if (!Platform.isMacOS && !Platform.isWindows && !Platform.isLinux) return;
    _prefs = await Prefs.load();
    _iconPath = await _iconRenderer.idleIcon();

    if (_native) {
      await StatusMenu.update(
        visible: true,
        imagePath: _iconPath,
        template: _iconTemplate,
        tooltip: appName,
      );
    } else {
      final icon = tray.TrayIcon.create();
      if (icon == null) return; // No tray on this desktop; the window stands alone.
      _tray = icon;
      final image = tray.Image.fromFile(_iconPath!);
      if (image != null) icon.icon = image;
      icon.setTooltip(appName);
      // The menu opens on either button, as it always has here: the right
      // click natively, the left through the event. Linux reports no tray
      // clicks at all — the panel holds them and opens the menu itself.
      icon.setContextMenuTrigger(tray.ContextMenuTrigger.rightClicked);
      icon.addListener((event) {
        if (event is tray.TrayIconClickedEvent) icon.openContextMenu();
      });
      icon.setVisible(true);
    }

    timer.addListener(_onTimer);
    timer.now.addListener(_tick);
    await _onTimer();

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
      _flowScores = flowScoresFromWindows(windows);
      await _updateIcon();
    } catch (_) {}
  }

  Future<void> _onTimer() async {
    final key = '${timer.current?.id}@${timer.since}';
    if (key != _timerKey) {
      _timerKey = key;
      await _updateIcon();
      // An open popover should show the change now, not at its next poll.
      await StatusMenu.timerChanged();
    }
    if (!_native) await _updateMenu();
    _tick();
  }

  Future<void> _updateIcon() async {
    final color = timer.current?.color;
    final rgb = color == null
        ? null
        : [(color.r * 255).round(), (color.g * 255).round(), (color.b * 255).round()];
    // Sparkline takes precedence whenever we have flow data — even idle,
    // a flat-but-recent flow line tells the user something. Fall back to
    // a plain dot when there's no data (fresh launch, API down).
    _iconPath = _flowScores.isNotEmpty
        ? await _iconRenderer.iconForSparkline(_flowScores, rgb)
        : await _iconRenderer.iconForProject(rgb);
    if (_native) {
      _lastTitle = null; // resend the title with the new icon
      _tick();
    } else {
      final image = tray.Image.fromFile(_iconPath!);
      if (image != null) _tray?.icon = image;
    }
  }

  void _tick() {
    final running = timer.running;
    final elapsed = running ? timer.elapsed : null;
    final title = menuBarTitle(
      _prefs?.menuBarShows ?? MenuBarShows.timeAndProject,
      project: timer.current?.name,
      elapsed: elapsed,
    );
    if (title != _lastTitle) {
      _lastTitle = title;
      if (_native) {
        StatusMenu.update(
          visible: true,
          title: title,
          imagePath: _iconPath,
          template: _iconTemplate,
          tooltip: running ? '$appName — ${timer.current!.name}' : appName,
        );
      } else {
        _tray?.setTitle(running ? '${formatTrayElapsed(elapsed!)}  ${timer.current!.name}' : '');
      }
    }

    // Mirror the running state into the macOS dock badge (whole minutes —
    // pixel-counting seconds in the dock would just be noise). Dedupe so we
    // skip the method-channel hop on the ~59 ticks/min where it's unchanged.
    final badge = dockBadgeForElapsed(elapsed, running: running);
    if (badge != _lastBadge) {
      MacAmbient.setDockBadge(badge);
      _lastBadge = badge;
    }
  }

  /// One labelled item: disabled for a line that only reads, otherwise
  /// running [onClick] on a click. Null when the native side cannot make
  /// one, which the assembly below skips.
  tray.MenuItem? _item(String label, {VoidCallback? onClick}) {
    final item = tray.MenuItem.createWithLabelAndType(label, tray.MenuItemType.normal);
    if (item == null) return null;
    if (onClick == null) {
      item.isEnabled = false;
    } else {
      item.addListener((event) {
        if (event is tray.MenuItemClickedEvent) onClick();
      });
    }
    return item;
  }

  /// The tray menu off macOS: what runs and Stop, or a Start submenu.
  Future<void> _updateMenu() async {
    final icon = _tray;
    if (icon == null) return;
    final menu = tray.Menu.create();
    if (menu == null) return;
    final kept = <tray.MenuItem>[];

    void add(tray.MenuItem? item) {
      if (item == null) return;
      menu.addItem(item);
      kept.add(item);
    }

    final current = timer.current;
    if (current != null) {
      add(_item('\u25cf ${current.name} \u2014 ${formatTrayElapsed(timer.elapsed)}'));
      menu.addSeparator();
      add(_item('\u25a0  Stop Timer', onClick: () => timer.stop()));
      menu.addSeparator();
    } else {
      add(_item('No timer running'));
      menu.addSeparator();
      final projects = timer.recentFirst.take(12).toList();
      if (projects.isNotEmpty) {
        final start = tray.MenuItem.createWithLabelAndType(
          '\u25b6  Start Timer',
          tray.MenuItemType.submenu,
        );
        final submenu = tray.Menu.create();
        if (start != null && submenu != null) {
          for (final p in projects) {
            final entry = _item(p.name, onClick: () => timer.startProject(p));
            if (entry != null) {
              submenu.addItem(entry);
              kept.add(entry);
            }
          }
          start.submenu = submenu;
          add(start);
          menu.addSeparator();
        }
      }
    }

    add(_item('Open $appName', onClick: () => onShowWindow()));
    menu.addSeparator();
    add(_item('Quit', onClick: () => exit(0)));

    icon.setContextMenu(menu);
    // Swap the kept references only once the new menu is in the tray, so the
    // old one's listeners outlive it rather than the other way round.
    _menu = menu;
    _menuItems = kept;
  }

  void dispose() {
    _flowTimer?.cancel();
    timer.removeListener(_onTimer);
    timer.now.removeListener(_tick);
    if (_native) {
      StatusMenu.update(visible: false);
    } else {
      _tray?.dispose();
      _tray = null;
      _menu = null;
      _menuItems = const [];
    }
    MacAmbient.setDockBadge(null);
  }
}
