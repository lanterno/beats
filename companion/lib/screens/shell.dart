import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:window_manager/window_manager.dart';

import '../brand.dart';
import '../services/api_client.dart';
import '../services/time_format.dart';
import '../state/hour.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'coach_screen.dart';
import 'flow_screen.dart';
import 'body_screen.dart';
import 'focus_screen.dart';
import 'palette.dart';
import 'settings_screen.dart';
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
  final HourController hour;
  final VoidCallback onUnpaired;
  final Section initial;

  const MainWindow({
    super.key,
    required this.client,
    required this.timer,
    required this.week,
    required this.hour,
    required this.onUnpaired,
    this.initial = Section.today,
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
    }
  }

  void find() {
    final prefix = Platform.isMacOS ? '⌘' : 'Ctrl ';
    showQuickStart(context, timer: widget.timer, actions: [
      for (final (i, s) in Section.values.indexed)
        PaletteAction('Open ${s.label}', s.icon, () => show(s), shortcut: '$prefix${i + 1}'),
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
            onOpenFlow: () => show(Section.flow),
            onOpenCoach: () => show(Section.coach),
            onOpenBody: () => show(Section.body),
            onFind: find,
          ),
        Section.flow => FlowScreen(client: widget.client),
        Section.coach => CoachScreen(client: widget.client, timer: widget.timer, week: widget.week),
        Section.body => BodyScreen(client: widget.client),
      };

  @override
  Widget build(BuildContext context) {
    final content = LayoutBuilder(builder: (context, box) {
      final wide = box.maxWidth >= 720;
      final page = AnimatedSwitcher(
        duration: const Duration(milliseconds: 180),
        child: KeyedSubtree(key: ValueKey(_section), child: _screen()),
      );
      if (!wide) {
        return Column(children: [
          Expanded(child: page),
          NavigationBar(
            selectedIndex: _section.index,
            onDestinationSelected: (i) => show(Section.values[i]),
            destinations: [
              for (final s in Section.values) NavigationDestination(icon: Icon(s.icon), label: s.label),
            ],
          ),
        ]);
      }
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
      body: SkyBackdrop(child: content),
    );

    if (!Platform.isMacOS) {
      return CallbackShortcuts(
        bindings: {
          for (final s in Section.values) SingleActivator(s.key, control: true): () => show(s),
          const SingleActivator(LogicalKeyboardKey.comma, control: true): openSettings,
          const SingleActivator(LogicalKeyboardKey.period, control: true): _stop,
          const SingleActivator(LogicalKeyboardKey.keyK, control: true): find,
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
                final ok = timer.error == null;
                return Container(
                  padding: const EdgeInsets.fromLTRB(14, 8, 6, 8),
                  decoration: BoxDecoration(
                    color: p.panel,
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(children: [
                    ProjectDot(color: ok ? p.leaf : p.persimmon, size: 8),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(ok ? 'Synced' : 'Can\'t reach the server',
                            style: SkyType.body(13, weight: FontWeight.w700)),
                        Text(host,
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

/// The app's mark: the first letter of its name on a sunlit square.
class BrandMark extends StatelessWidget {
  final double size;
  const BrandMark({super.key, this.size = 30});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: p.sun, borderRadius: BorderRadius.circular(size / 3)),
        child: Text(appName.characters.first,
            style: SkyType.display(size * 0.55).copyWith(color: p.onSun)),
      ),
    );
  }
}
