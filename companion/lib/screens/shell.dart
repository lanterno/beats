import 'dart:io';
import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';
import 'package:window_manager/window_manager.dart';

import '../brand.dart';
import '../services/api_client.dart';
import '../services/time_format.dart';
import '../state/hour.dart';
import '../state/idle_watcher.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import '../ui/sync_note.dart';
import 'coach_screen.dart';
import 'flow_screen.dart';
import 'body_screen.dart';
import 'focus_screen.dart';
import 'log_session_dialog.dart';
import 'palette.dart';
import 'settings_screen.dart';
import 'start_sheet.dart';
import 'timer_actions.dart';
import 'today_screen.dart';

enum Section { today, flow, coach, body }

extension on Section {
  String get label => switch (this) {
        Section.today => 'Today',
        Section.flow => 'Flow',
        Section.coach => 'Coach',
        Section.body => 'Body',
      };

  IconData get icon => switch (this) {
        Section.today => Icons.wb_sunny_outlined,
        Section.flow => Icons.show_chart_rounded,
        Section.coach => Icons.chat_bubble_outline_rounded,
        Section.body => Icons.favorite_border_rounded,
      };

  LogicalKeyboardKey get key => switch (this) {
        Section.today => LogicalKeyboardKey.digit1,
        Section.flow => LogicalKeyboardKey.digit2,
        Section.coach => LogicalKeyboardKey.digit3,
        Section.body => LogicalKeyboardKey.digit4,
      };
}

/// The main window: a sidebar of four places and the one being looked at,
/// on the sky. On a Mac the title bar is hidden and the traffic lights sit
/// in the sidebar's top corner; on a narrow window the sidebar becomes a
/// bottom bar.
class MainWindow extends StatefulWidget {
  final ApiClient client;
  final TimerController timer;
  final WeekController week;
  final IdleWatcher idle;
  final HourController hour;
  final VoidCallback onUnpaired;
  final Section initial;

  /// Showing sample data: a banner says so, with the way back to pairing.
  final bool sample;

  const MainWindow({
    super.key,
    required this.client,
    required this.timer,
    required this.week,
    required this.idle,
    required this.hour,
    required this.onUnpaired,
    this.initial = Section.today,
    this.sample = false,
  });

  @override
  State<MainWindow> createState() => MainWindowState();
}

class MainWindowState extends State<MainWindow> {
  late Section _section = widget.initial;

  void show(Section s) => setState(() => _section = s);

  void openSettings() {
    final nav = Navigator.of(context);
    nav.popUntil((r) => r.isFirst);
    nav.push(MaterialPageRoute(
      builder: (_) => SettingsScreen(
        client: widget.client,
        timer: widget.timer,
        hour: widget.hour,
        onUnpaired: () {
          nav.popUntil((r) => r.isFirst);
          widget.onUnpaired();
        },
      ),
    ));
  }

  void openFocus() {
    final nav = Navigator.of(context);
    nav.popUntil((r) => r.isFirst);
    nav.push(PageRouteBuilder(
      transitionDuration: const Duration(milliseconds: 350),
      pageBuilder: (_, _, _) => FocusScreen(timer: widget.timer),
      transitionsBuilder: (_, animation, _, child) => FadeTransition(opacity: animation, child: child),
    ));
  }

  /// Opens a place or a route by name, for the menu bar popover.
  void showByName({String? section, String? route}) {
    final s = Section.values.where((s) => s.name == section).firstOrNull;
    if (s != null) {
      Navigator.of(context).popUntil((r) => r.isFirst);
      show(s);
    }
    switch (route) {
      case 'settings':
        openSettings();
      case 'focus':
        openFocus();
      case 'log':
        logSession();
      case 'find':
        find();
    }
  }

  void logSession() => showLogSession(context, client: widget.client, timer: widget.timer, week: widget.week);

  /// Start, switch or find: the bottom sheet on a phone, the palette on a
  /// wider window.
  void find() {
    if (MediaQuery.sizeOf(context).width < 720) {
      Navigator.of(context).popUntil((r) => r.isFirst);
      showStartSheet(context, timer: widget.timer, week: widget.week, onLog: logSession, onFocus: openFocus);
      return;
    }
    final prefix = Platform.isMacOS ? '⌘' : 'Ctrl ';
    showQuickStart(context, timer: widget.timer, actions: [
      for (final (i, s) in Section.values.indexed)
        PaletteAction('Open ${s.label}', s.icon, () => show(s), shortcut: '$prefix${i + 1}'),
      PaletteAction('Log time you forgot…', Icons.history_rounded, logSession, shortcut: '${prefix}L'),
      PaletteAction('Focus mode', Icons.fullscreen_rounded, openFocus, shortcut: '⇧${prefix}F'),
      PaletteAction('Settings', Icons.settings_outlined, openSettings, shortcut: '$prefix,'),
    ]);
  }

  void _stop() {
    if (widget.timer.running) TimerActions.stop(context, widget.timer);
  }

  Widget _screen() => switch (_section) {
        Section.today => TodayScreen(
            client: widget.client,
            timer: widget.timer,
            week: widget.week,
            idle: widget.idle,
            onOpenFlow: () => show(Section.flow),
            onOpenCoach: () => show(Section.coach),
            onOpenBody: () => show(Section.body),
            onFind: find,
            onSettings: openSettings,
          ),
        Section.flow => FlowScreen(client: widget.client),
        Section.coach => CoachScreen(client: widget.client, timer: widget.timer, week: widget.week),
        Section.body => BodyScreen(client: widget.client),
      };

  /// One thumb: a floating tab bar at the window's foot (a gold start
  /// button in the middle) and, away from Today, the running timer as a
  /// pill above it. They are the Scaffold's bottom bar with the body drawn
  /// behind them, so the page learns what they cover from MediaQuery's
  /// bottom padding, snackbars float above them, and the keyboard covers
  /// them rather than pushing them up.
  Widget _phoneBars(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.timer,
      builder: (context, _) {
        final pill = widget.timer.running && _section != Section.today;
        return Padding(
          padding: EdgeInsets.fromLTRB(14, 0, 14, math.max(MediaQuery.paddingOf(context).bottom, 12.0)),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            AnimatedSize(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeOut,
              alignment: Alignment.bottomCenter,
              child: pill
                  ? Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _RunningPill(timer: widget.timer, onOpen: () => show(Section.today)),
                    )
                  : const SizedBox(width: double.infinity),
            ),
            _TabBar(section: _section, onSection: show, onStart: find),
          ]),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 720;
    final content = Builder(builder: (context) {
      Widget page = AnimatedSwitcher(
        duration: const Duration(milliseconds: 180),
        child: KeyedSubtree(key: ValueKey(_section), child: _screen()),
      );
      if (widget.sample) {
        page = Column(children: [
          SafeArea(bottom: false, child: _SampleBanner(onPair: widget.onUnpaired)),
          Expanded(child: MediaQuery.removePadding(context: context, removeTop: true, child: page)),
        ]);
      }
      if (!wide) return page;
      return Row(children: [
        _Sidebar(
          section: _section,
          onSection: show,
          onSettings: openSettings,
          timer: widget.timer,
          week: widget.week,
          host: Uri.tryParse(widget.client.baseUrl)?.host ?? widget.client.baseUrl,
        ),
        Expanded(
          child: Stack(children: [
            Positioned.fill(child: page),
            if (Platform.isMacOS)
              const Positioned(top: 0, left: 0, right: 0, height: 28, child: DragToMoveArea(child: SizedBox.expand())),
          ]),
        ),
      ]);
    });

    final window = Scaffold(
      backgroundColor: Colors.transparent,
      extendBody: true,
      bottomNavigationBar: wide ? null : _phoneBars(context),
      body: SkyBackdrop(child: content),
    );

    if (!Platform.isMacOS) {
      return CallbackShortcuts(
        bindings: {
          for (final s in Section.values) SingleActivator(s.key, control: true): () => show(s),
          const SingleActivator(LogicalKeyboardKey.comma, control: true): openSettings,
          const SingleActivator(LogicalKeyboardKey.period, control: true): _stop,
          const SingleActivator(LogicalKeyboardKey.keyK, control: true): find,
          const SingleActivator(LogicalKeyboardKey.keyL, control: true): logSession,
          const SingleActivator(LogicalKeyboardKey.keyF, control: true, shift: true): openFocus,
        },
        child: Focus(autofocus: true, child: window),
      );
    }

    return ListenableBuilder(
      listenable: widget.timer,
      builder: (context, _) => PlatformMenuBar(
        menus: [
          PlatformMenu(label: appName, menus: [
            const PlatformMenuItemGroup(members: [
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.about),
            ]),
            PlatformMenuItemGroup(members: [
              PlatformMenuItem(
                label: 'Settings…',
                shortcut: const SingleActivator(LogicalKeyboardKey.comma, meta: true),
                onSelected: openSettings,
              ),
            ]),
            const PlatformMenuItemGroup(members: [
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.hide),
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.hideOtherApplications),
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.showAllApplications),
            ]),
            const PlatformMenuItemGroup(members: [
              PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.quit),
            ]),
          ]),
          PlatformMenu(label: 'Timer', menus: [
            PlatformMenuItem(
              label: 'Start or Find…',
              shortcut: const SingleActivator(LogicalKeyboardKey.keyK, meta: true),
              onSelected: find,
            ),
            PlatformMenuItem(
              label: 'Log Forgotten Time…',
              shortcut: const SingleActivator(LogicalKeyboardKey.keyL, meta: true),
              onSelected: logSession,
            ),
            PlatformMenuItem(
              label: widget.timer.running ? 'Stop ${widget.timer.current!.name}' : 'Stop',
              shortcut: const SingleActivator(LogicalKeyboardKey.period, meta: true),
              onSelected: widget.timer.running ? _stop : null,
            ),
          ]),
          PlatformMenu(label: 'View', menus: [
            PlatformMenuItemGroup(members: [
              for (final s in Section.values)
                PlatformMenuItem(
                  label: s.label,
                  shortcut: SingleActivator(s.key, meta: true),
                  onSelected: () => show(s),
                ),
            ]),
            PlatformMenuItemGroup(members: [
              PlatformMenuItem(
                label: 'Focus Mode',
                shortcut: const SingleActivator(LogicalKeyboardKey.keyF, meta: true, shift: true),
                onSelected: openFocus,
              ),
              const PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.toggleFullScreen),
            ]),
          ]),
          const PlatformMenu(label: 'Window', menus: [
            PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.minimizeWindow),
            PlatformProvidedMenuItem(type: PlatformProvidedMenuItemType.zoomWindow),
          ]),
        ],
        child: window,
      ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  final Section section;
  final ValueChanged<Section> onSection;
  final VoidCallback onSettings;
  final TimerController timer;
  final WeekController week;
  final String host;

  const _Sidebar({
    required this.section,
    required this.onSection,
    required this.onSettings,
    required this.timer,
    required this.week,
    required this.host,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final shortcutPrefix = Platform.isMacOS ? '⌘' : 'Ctrl ';
    return Container(
      width: 236,
      decoration: BoxDecoration(
        color: p.sidebar,
        border: Border(right: BorderSide(color: p.hairline)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Room for the traffic lights, and somewhere to drag the window by.
          SizedBox(
            height: Platform.isMacOS ? 48 : 16,
            child: Platform.isMacOS ? const DragToMoveArea(child: SizedBox.expand()) : null,
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            child: Row(children: [
              const BrandMark(size: 30),
              const SizedBox(width: 10),
              Text(appName, style: SkyType.display(17)),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Column(children: [
              for (final (i, s) in Section.values.indexed)
                _NavItem(
                  label: s.label,
                  icon: s.icon,
                  shortcut: '$shortcutPrefix${i + 1}',
                  selected: s == section,
                  onTap: () => onSection(s),
                ),
            ]),
          ),
          const SizedBox(height: 22),
          Expanded(
            child: ListenableBuilder(
              listenable: Listenable.merge([timer, week]),
              builder: (context, _) => ListView(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  if (timer.running) ...[
                    _RunningTile(timer: timer, onTap: () => onSection(Section.today)),
                    const SizedBox(height: 18),
                  ],
                  if (week.weeks.any((w) => w.worked > 0)) ...[
                    Padding(
                      padding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
                      child: Text('This week',
                          style: SkyType.body(12, weight: FontWeight.w700).copyWith(color: p.inkMuted)),
                    ),
                    for (final w in week.weeks.where((w) => w.worked > 0))
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                        child: Row(children: [
                          ProjectDot(color: w.project.color),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(w.project.name,
                                overflow: TextOverflow.ellipsis, style: SkyType.body(14)),
                          ),
                          Text(formatMinutes((w.worked * 60).round()),
                              style: SkyType.figure(13, weight: FontWeight.w500).copyWith(color: p.inkMuted)),
                        ]),
                      ),
                  ],
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
            child: ListenableBuilder(
              listenable: timer,
              builder: (context, _) {
                final line = timer.syncLine;
                return Container(
                  padding: const EdgeInsets.fromLTRB(14, 8, 6, 8),
                  decoration: BoxDecoration(
                    color: p.panel,
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(children: [
                    SyncDot(line.tone),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(line.title, style: SkyType.body(13, weight: FontWeight.w700)),
                        Text(line.detail ?? host,
                            overflow: TextOverflow.ellipsis,
                            style: SkyType.body(12).copyWith(color: p.inkMuted)),
                      ]),
                    ),
                    IconButton(
                      tooltip: 'Settings',
                      onPressed: onSettings,
                      icon: Icon(Icons.settings_outlined, size: 18, color: p.inkMuted),
                    ),
                  ]),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Says the data on screen is made up, and offers the way to real data.
class _SampleBanner extends StatelessWidget {
  final VoidCallback onPair;
  const _SampleBanner({required this.onPair});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.fromLTRB(16, 4, 6, 4),
      decoration: BoxDecoration(color: p.sun.withValues(alpha: 0.9), borderRadius: BorderRadius.circular(999)),
      child: Row(children: [
        Icon(Icons.visibility_outlined, size: 18, color: p.onSun),
        const SizedBox(width: 10),
        Expanded(
          child: Text('Sample data — nothing here is real',
              style: SkyType.body(13, weight: FontWeight.w700).copyWith(color: p.onSun)),
        ),
        TextButton(
          onPressed: onPair,
          style: TextButton.styleFrom(foregroundColor: p.onSun, shape: const StadiumBorder()),
          child: Text('Pair', style: SkyType.body(14, weight: FontWeight.w700).copyWith(
            decoration: TextDecoration.underline,
            decorationColor: p.onSun.withValues(alpha: 0.4),
          )),
        ),
      ]),
    );
  }
}

/// The phone's places, on a floating pill: Today and Flow, the start
/// button, Coach and Body.
class _TabBar extends StatelessWidget {
  static const height = 68.0;

  final Section section;
  final ValueChanged<Section> onSection;
  final VoidCallback onStart;
  const _TabBar({required this.section, required this.onSection, required this.onStart});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    Widget tab(Section s) {
      final on = s == section;
      return Semantics(
        selected: on,
        button: true,
        label: s.label,
        excludeSemantics: true,
        child: Material(
          color: on ? p.washStrong : Colors.transparent,
          shape: const StadiumBorder(),
          child: InkWell(
            customBorder: const StadiumBorder(),
            onTap: () => onSection(s),
            child: SizedBox(
              width: 64,
              height: 52,
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(s.icon, size: 20, color: on ? p.ink : p.inkMuted),
                const SizedBox(height: 3),
                Text(s.label,
                    style: SkyType.body(11, weight: on ? FontWeight.w700 : FontWeight.w400, height: 1.2)
                        .copyWith(color: on ? p.ink : p.inkMuted)),
              ]),
            ),
          ),
        ),
      );
    }

    return Container(
      height: height,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: p.panel.withValues(alpha: 0.97),
        borderRadius: BorderRadius.circular(999),
        boxShadow: const [
          BoxShadow(color: Color(0x142B3A44), blurRadius: 2, offset: Offset(0, 1)),
          BoxShadow(color: Color(0x292B3A44), blurRadius: 32, offset: Offset(0, 12)),
        ],
      ),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        tab(Section.today),
        tab(Section.flow),
        Tooltip(
          message: 'Start or switch',
          child: Material(
            color: p.sun,
            shape: const CircleBorder(),
            elevation: 3,
            shadowColor: p.sun.withValues(alpha: 0.6),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: onStart,
              child: SizedBox.square(dimension: 56, child: Icon(Icons.add_rounded, size: 28, color: p.onSun)),
            ),
          ),
        ),
        tab(Section.coach),
        tab(Section.body),
      ]),
    );
  }
}

/// What runs, on every tab but Today: its ring, its name, the clock, and
/// Stop. A tap anywhere else opens Today.
class _RunningPill extends StatelessWidget {
  static const height = 56.0;

  final TimerController timer;
  final VoidCallback onOpen;
  const _RunningPill({required this.timer, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final project = timer.current;
    if (project == null) return const SizedBox.shrink();
    // The pill is the ink colour, so its text is the panel's: dark on light
    // in the afternoon, light on dark at dusk.
    final fg = p.panel.withValues(alpha: 1);
    return Material(
      color: p.ink,
      shape: const StadiumBorder(),
      elevation: 6,
      shadowColor: const Color(0x552B3A44),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onOpen,
        child: SizedBox(
          height: height,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
            child: Row(children: [
              RingGlyph(color: project.color, track: fg.withValues(alpha: 0.25)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(project.name,
                    overflow: TextOverflow.ellipsis,
                    style: SkyType.body(14, weight: FontWeight.w700).copyWith(color: fg)),
              ),
              ValueListenableBuilder(
                valueListenable: timer.now,
                builder: (context, _, _) => Semantics(
                  label: 'Running for ${formatDuration(timer.elapsed)}',
                  excludeSemantics: true,
                  child: Text(formatClock(timer.elapsed), style: SkyType.figure(17, weight: FontWeight.w700).copyWith(color: fg)),
                ),
              ),
              const SizedBox(width: 10),
              IconButton(
                tooltip: 'Stop ${project.name}',
                onPressed: () => TimerActions.stop(context, timer),
                icon: Icon(Icons.stop_rounded, color: p.onSun),
                style: IconButton.styleFrom(backgroundColor: p.sun, fixedSize: const Size.square(44)),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final String label;
  final IconData icon;
  final String shortcut;
  final bool selected;
  final VoidCallback onTap;

  const _NavItem({
    required this.label,
    required this.icon,
    required this.shortcut,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Semantics(
        selected: selected,
        child: TextButton(
          onPressed: onTap,
          style: TextButton.styleFrom(
            backgroundColor: selected ? p.washStrong : Colors.transparent,
            foregroundColor: p.ink,
            shape: const StadiumBorder(),
            minimumSize: const Size.fromHeight(40),
            padding: const EdgeInsets.symmetric(horizontal: 14),
            alignment: Alignment.centerLeft,
          ),
          child: Row(children: [
            Icon(icon, size: 18),
            const SizedBox(width: 12),
            Expanded(
              child: Text(label, style: SkyType.body(14, weight: selected ? FontWeight.w700 : FontWeight.w400)),
            ),
            Text(shortcut, style: SkyType.body(12).copyWith(color: p.inkMuted)),
          ]),
        ),
      ),
    );
  }
}

class _RunningTile extends StatelessWidget {
  final TimerController timer;
  final VoidCallback onTap;
  const _RunningTile({required this.timer, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final project = timer.current!;
    return Material(
      color: project.color.withValues(alpha: 0.16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(children: [
            ProjectDot(color: project.color),
            const SizedBox(width: 10),
            Expanded(
              child: Text(project.name,
                  overflow: TextOverflow.ellipsis, style: SkyType.body(14, weight: FontWeight.w700)),
            ),
            ValueListenableBuilder(
              valueListenable: timer.now,
              builder: (context, _, _) => Text(formatShortClock(timer.elapsed), style: SkyType.figure(14)),
            ),
          ]),
        ),
      ),
    );
  }
}

/// The app's mark, the day ring (shared/brand/mark.svg): a faint ring, a
/// gold arc from twelve round two thirds of the dial, and the sun where it
/// ends, on a navy tile in either hour.
class BrandMark extends StatelessWidget {
  final double size;
  const BrandMark({super.key, this.size = 30});

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: CustomPaint(size: Size.square(size), painter: const _DayRingPainter()),
    );
  }
}

class _DayRingPainter extends CustomPainter {
  const _DayRingPainter();

  static const _tile = Color(0xFF1A2446);
  static const _track = Color(0xFF2E3E6E);
  static const _sun = Color(0xFFF5C35E);

  @override
  void paint(Canvas canvas, Size size) {
    // Drawn on the SVG's 120 grid.
    final k = size.width / 120;
    canvas.drawRRect(
      RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(27 * k)),
      Paint()..color = _tile,
    );
    final center = Offset(60 * k, 60 * k);
    final radius = 34 * k;
    Paint stroke(Color c) => Paint()
      ..color = c
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8 * k
      ..strokeCap = StrokeCap.round;
    const start = -math.pi / 2;
    const sweep = math.pi * 4 / 3;
    canvas.drawCircle(center, radius, stroke(_track));
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), start, sweep, false, stroke(_sun));
    final end = center + Offset(math.cos(start + sweep), math.sin(start + sweep)) * radius;
    canvas.drawCircle(end, 9 * k, Paint()..color = _sun);
  }

  @override
  bool shouldRepaint(_DayRingPainter oldDelegate) => false;
}
