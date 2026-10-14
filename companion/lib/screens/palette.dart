import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/quick_parse.dart';
import '../services/time_format.dart';
import '../state/timer_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'timer_actions.dart';

/// Something the palette can do besides the timer: open a place, focus mode.
class PaletteAction {
  final String label;
  final IconData icon;
  final String? shortcut;
  final VoidCallback run;
  const PaletteAction(this.label, this.icon, this.run, {this.shortcut});
}

/// Opens the quick-start palette over [context]: type a project (and a time)
/// and press Return. See quick_parse.dart for what it understands.
Future<void> showQuickStart(
  BuildContext context, {
  required TimerController timer,
  List<PaletteAction> actions = const [],
}) {
  return showDialog(
    context: context,
    barrierColor: const Color(0x332B3A44),
    builder: (_) => QuickStartPalette(host: context, timer: timer, actions: actions),
  );
}

sealed class _Item {}

class _StartItem extends _Item {
  final Project project;
  _StartItem(this.project);
}

class _StopItem extends _Item {}

class _ActionItem extends _Item {
  final PaletteAction action;
  _ActionItem(this.action);
}

class QuickStartPalette extends StatefulWidget {
  /// Where confirmations land once the palette has closed.
  final BuildContext host;
  final TimerController timer;
  final List<PaletteAction> actions;

  /// Called after the palette runs something, instead of popping a route —
  /// for the menu bar popover, which is not a route.
  final VoidCallback? onDone;

  const QuickStartPalette({
    super.key,
    required this.host,
    required this.timer,
    this.actions = const [],
    this.onDone,
  });

  @override
  State<QuickStartPalette> createState() => _QuickStartPaletteState();
}

class _QuickStartPaletteState extends State<QuickStartPalette> {
  final _text = TextEditingController();
  int _selected = 0;

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() => _selected = 0));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  QuickCommand get _command => parseQuick(_text.text, DateTime.now());

  List<_Item> get _items {
    final cmd = _command;
    final timer = widget.timer;
    if (cmd.verb == QuickVerb.stop) return timer.running ? [_StopItem()] : [];
    final projects = timer.recentFirst;
    final matches = rankMatches(cmd.query, [for (final p in projects) p.name]);
    return [
      for (final i in matches.take(6))
        if (projects[i].id != timer.current?.id || cmd.at != null) _StartItem(projects[i]),
      if (cmd.at == null)
        for (final i in rankMatches(cmd.query, [for (final a in widget.actions) a.label]))
          _ActionItem(widget.actions[i]),
    ];
  }

  void _close() {
    if (widget.onDone != null) {
      _text.clear();
      widget.onDone!();
    } else {
      Navigator.of(context).pop();
    }
  }

  void _run(_Item item) {
    final cmd = _command;
    if (cmd.problem != null && item is! _ActionItem) return;
    _close();
    final host = widget.host;
    if (!host.mounted) return;
    switch (item) {
      case _StartItem(:final project):
        TimerActions.start(host, widget.timer, project, at: cmd.at);
      case _StopItem():
        TimerActions.stop(host, widget.timer, at: cmd.at);
      case _ActionItem(:final action):
        action.run();
    }
  }

  KeyEventResult _onKey(FocusNode _, KeyEvent e) {
    if (e is! KeyDownEvent && e is! KeyRepeatEvent) return KeyEventResult.ignored;
    final n = _items.length;
    if (e.logicalKey == LogicalKeyboardKey.arrowDown && n > 0) {
      setState(() => _selected = (_selected + 1) % n);
      return KeyEventResult.handled;
    }
    if (e.logicalKey == LogicalKeyboardKey.arrowUp && n > 0) {
      setState(() => _selected = (_selected - 1 + n) % n);
      return KeyEventResult.handled;
    }
    if (e.logicalKey == LogicalKeyboardKey.escape) {
      _close();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  /// The sentence above the list: what Return will do.
  (String, String?)? _preview(_Item? item) {
    final cmd = _command;
    final timer = widget.timer;
    final now = DateTime.now();
    final at = cmd.at;
    final when = at == null ? '' : ' from ${formatTimeOfDay(at)}';
    switch (item) {
      case _StartItem(:final project):
        final current = timer.current;
        if (current != null && current.id != project.id) {
          final stopAt = at ?? now;
          final ran = stopAt.toUtc().difference(timer.since!);
          return (
            'Switch to ${project.name}$when',
            'Stops ${current.name}${at == null ? '' : ' at ${formatTimeOfDay(at)}'} '
                '(${formatDuration(ran)})${at == null ? '' : ' · ${project.name} starts ${_ago(now.difference(at))}'}',
          );
        }
        if (current != null && current.id == project.id && at != null) {
          return ('Restart ${project.name}$when', 'Closes the running session and opens a new one');
        }
        return ('Start ${project.name}$when', at == null ? null : 'Starts ${_ago(now.difference(at))}');
      case _StopItem():
        final stopAt = at ?? now;
        return (
          'Stop ${timer.current!.name}${at == null ? '' : ' at ${formatTimeOfDay(at)}'}',
          'Logs ${formatDuration(stopAt.toUtc().difference(timer.since!))}',
        );
      case _ActionItem(:final action):
        return (action.label, null);
      case null:
        return null;
    }
  }

  String _ago(Duration d) {
    if (d.inMinutes < 1) return 'now';
    return '${formatDuration(d)} ago';
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final items = _items;
    final selected = items.isEmpty ? null : items[_selected.clamp(0, items.length - 1)];
    final preview = _preview(selected);
    final problem = _command.problem;
    final starts = items.whereType<_StartItem>().toList();
    final acts = items.whereType<_ActionItem>().toList();

    Widget row(_Item item, Widget leading, String label, {String? trailing}) {
      final on = item == selected;
      return Material(
        color: on ? p.washStrong : Colors.transparent,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: () => _run(item),
          onHover: (h) {
            if (h) setState(() => _selected = items.indexOf(item));
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
            child: Row(children: [
              SizedBox(width: 20, child: Center(child: leading)),
              const SizedBox(width: 12),
              Expanded(child: Text(label, style: SkyType.body(15))),
              if (trailing != null) Text(trailing, style: SkyType.body(13).copyWith(color: p.inkMuted)),
            ]),
          ),
        ),
      );
    }

    Widget section(String t) => Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
          child: Text(t, style: SkyType.body(12, weight: FontWeight.w700).copyWith(color: p.inkMuted)),
        );

    final card = Container(
      width: 640,
      constraints: const BoxConstraints(maxHeight: 560),
      decoration: BoxDecoration(
        color: p.panel.withValues(alpha: 1),
        borderRadius: BorderRadius.circular(26),
        boxShadow: const [BoxShadow(color: Color(0x592B3A44), blurRadius: 80, offset: Offset(0, 30))],
      ),
      clipBehavior: Clip.antiAlias,
      child: Focus(
        onKeyEvent: _onKey,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
            child: Row(children: [
              Icon(Icons.search_rounded, color: p.inkMuted),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _text,
                  autofocus: true,
                  style: SkyType.display(22, weight: FontWeight.w500),
                  decoration: InputDecoration(
                    hintText: widget.timer.running ? 'Switch, stop, or “kite from 11:00”' : 'Start a project, or “spanish 25m ago”',
                    hintStyle: SkyType.display(22, weight: FontWeight.w400).copyWith(color: p.inkMuted),
                    filled: false,
                    border: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                  ),
                  onSubmitted: (_) {
                    if (selected != null) _run(selected);
                  },
                ),
              ),
            ]),
          ),
          Divider(height: 1, color: p.hairline),
          if (preview != null)
            Container(
              margin: const EdgeInsets.fromLTRB(16, 14, 16, 4),
              padding: const EdgeInsets.fromLTRB(16, 12, 12, 12),
              decoration: BoxDecoration(
                color: problem != null
                    ? p.persimmon.withValues(alpha: 0.14)
                    : (selected is _StartItem ? selected.project.color : p.sun).withValues(alpha: 0.16),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Row(children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(problem ?? preview.$1, style: SkyType.body(16, weight: FontWeight.w700)
                        .copyWith(color: problem != null ? p.persimmonInk : p.ink)),
                    if (problem == null && preview.$2 != null) ...[
                      const SizedBox(height: 2),
                      Text(preview.$2!, style: SkyType.body(13).copyWith(color: p.inkOnSky)),
                    ],
                  ]),
                ),
                if (problem == null) Chip2('↵', background: p.ink, foreground: p.panel.withValues(alpha: 1), bold: true),
              ]),
            ),
          Flexible(
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.fromLTRB(16, 6, 16, 10),
              children: [
                if (selected is _StopItem) ...[
                  section('Timer'),
                  row(selected, Icon(Icons.stop_rounded, size: 18, color: p.ink), 'Stop ${widget.timer.current!.name}'),
                ],
                if (starts.isNotEmpty) ...[
                  section('Projects'),
                  for (final s in starts)
                    row(s, ProjectDot(color: s.project.color), s.project.name, trailing: s.project.kindLabel),
                ],
                if (acts.isNotEmpty) ...[
                  section('Go to'),
                  for (final a in acts)
                    row(a, Icon(a.action.icon, size: 18, color: p.inkMuted), a.action.label, trailing: a.action.shortcut),
                ],
                if (items.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(
                      _command.verb == QuickVerb.stop ? 'Nothing is running.' : 'No project matches “${_command.query}”.',
                      style: SkyType.body(14).copyWith(color: p.inkMuted),
                    ),
                  ),
              ],
            ),
          ),
          Container(
            color: p.wash,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
            child: Row(children: [
              Text('↵ Run   ↑↓ Move   esc Close', style: SkyType.body(12).copyWith(color: p.inkOnSky)),
              const Spacer(),
              Text('Try “stop at 17:30”', style: SkyType.body(12).copyWith(color: p.inkMuted)),
            ]),
          ),
        ]),
      ),
    );

    if (widget.onDone != null) return card;
    return Align(
      alignment: const Alignment(0, -0.55),
      child: Material(type: MaterialType.transparency, child: card),
    );
  }
}
