import 'package:flutter/material.dart';

import '../services/quick_parse.dart';
import '../services/quick_preview.dart';
import '../services/time_format.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'timer_actions.dart';

/// The phone's quick start, from the tab bar's gold button: the projects as
/// tiles to tap, and above them the palette's field for a time ("kite from
/// 11:00", "spanish 25m ago", "stop at 17:30"), with a card saying what it
/// will do before it does it.
Future<void> showStartSheet(
  BuildContext context, {
  required TimerController timer,
  required WeekController week,
  required VoidCallback onLog,
  required VoidCallback onFocus,
}) {
  final p = context.sky;
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    backgroundColor: p.panel.withValues(alpha: 1),
    barrierColor: const Color(0x6B1A2446),
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(32))),
    builder: (_) => StartSheet(host: context, timer: timer, week: week, onLog: onLog, onFocus: onFocus),
  );
}

class StartSheet extends StatefulWidget {
  /// Where confirmations land once the sheet has closed.
  final BuildContext host;
  final TimerController timer;
  final WeekController week;
  final VoidCallback onLog;
  final VoidCallback onFocus;

  const StartSheet({
    super.key,
    required this.host,
    required this.timer,
    required this.week,
    required this.onLog,
    required this.onFocus,
  });

  @override
  State<StartSheet> createState() => _StartSheetState();
}

class _StartSheetState extends State<StartSheet> {
  final _text = TextEditingController();

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  bool get _typed => _text.text.trim().isNotEmpty;

  QuickCommand get _command => parseQuick(_text.text, DateTime.now());

  /// The projects to show: all of them most recent first, or those the
  /// words match, best first.
  List<Project> get _projects {
    final all = widget.timer.recentFirst;
    final cmd = _command;
    if (!_typed || cmd.verb == QuickVerb.stop) return all;
    return [for (final i in rankMatches(cmd.query, [for (final p in all) p.name])) all[i]];
  }

  void _close() => Navigator.of(context).pop();

  void _start(Project project) {
    final cmd = _command;
    if (cmd.problem != null) return;
    final at = _typed ? cmd.at : null;
    if (project.id == widget.timer.current?.id && at == null) return;
    _close();
    if (widget.host.mounted) TimerActions.start(widget.host, widget.timer, project, at: at);
  }

  void _stop() {
    final cmd = _command;
    if (cmd.problem != null) return;
    _close();
    if (widget.host.mounted) TimerActions.stop(widget.host, widget.timer, at: cmd.at);
  }

  /// A few things to type, made from this person's own projects.
  List<String> get _examples {
    final timer = widget.timer;
    String word(Project p) => p.name.toLowerCase().split(RegExp(r'\s+')).last;
    final others = timer.recentFirst.where((p) => p.id != timer.current?.id).toList();
    final now = DateTime.now();
    final earlier = now.subtract(Duration(minutes: 20 + now.minute % 5));
    return [
      if (others.isNotEmpty) '${word(others.first)} from ${formatTimeOfDay(earlier)}',
      if (others.length > 1) '${word(others[1])} 25m ago',
      if (timer.running) 'stop 10m ago',
    ];
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: Listenable.merge([widget.timer, widget.week]),
        builder: (context, _) => _sheet(context),
      );

  Widget _sheet(BuildContext context) {
    final p = context.sky;
    final timer = widget.timer;
    final projects = _projects;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.86),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
          children: [
            Row(children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(timer.running ? 'Start or switch' : 'Start', style: SkyType.display(22)),
                ),
              ),
              RoundIconButton(icon: Icons.close_rounded, tooltip: 'Close', size: 44, onPressed: _close),
            ]),
            const SizedBox(height: 14),
            TextField(
              controller: _text,
              textInputAction: TextInputAction.go,
              autocorrect: false,
              style: SkyType.body(17),
              decoration: InputDecoration(
                labelText: 'A project, and a time if it wasn\'t now',
                floatingLabelBehavior: FloatingLabelBehavior.never,
                prefixIcon: Icon(Icons.search_rounded, color: p.inkMuted),
                suffixIcon: _typed
                    ? IconButton(tooltip: 'Clear', icon: const Icon(Icons.close_rounded), onPressed: _text.clear)
                    : null,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              ),
              onSubmitted: (_) => _submit(projects),
            ),
            const SizedBox(height: 10),
            if (!_typed)
              Wrap(spacing: 6, runSpacing: 6, children: [
                for (final e in _examples)
                  ActionChip(
                    label: Text(e, style: SkyType.body(13).copyWith(color: p.inkOnSky)),
                    backgroundColor: Colors.transparent,
                    side: BorderSide(color: p.hairline, width: 1.5),
                    shape: const StadiumBorder(),
                    onPressed: () => _text.value = TextEditingValue(
                      text: e,
                      selection: TextSelection.collapsed(offset: e.length),
                    ),
                  ),
              ])
            else
              _card(context, projects),
            const SizedBox(height: 18),
            Text(_typed ? 'Matches' : 'Your projects',
                style: SkyType.body(13, weight: FontWeight.w700).copyWith(color: p.inkMuted)),
            const SizedBox(height: 10),
            if (projects.isEmpty)
              Text(
                timer.projects.isEmpty ? 'Create a project on the web to start tracking.' : 'No project matches.',
                style: SkyType.body(14).copyWith(color: p.inkMuted),
              )
            else
              _tiles(context, projects),
            const SizedBox(height: 18),
            _links(context),
          ],
        ),
      ),
    );
  }

  void _submit(List<Project> projects) {
    if (_command.verb == QuickVerb.stop) {
      if (widget.timer.running) _stop();
    } else if (projects.isNotEmpty) {
      _start(projects.first);
    }
  }

  /// What the words mean, and the one button that does it.
  Widget _card(BuildContext context, List<Project> projects) {
    final p = context.sky;
    final timer = widget.timer;
    final cmd = _command;
    final now = DateTime.now();

    late final String title;
    String? detail;
    String? action;
    VoidCallback? run;
    var tint = p.sun;

    if (cmd.verb == QuickVerb.stop) {
      if (timer.running) {
        final q = previewStop(running: timer.current!.name, since: timer.since!, now: now, at: cmd.at);
        (title, detail, action, run) = (q.title, q.detail, 'Stop', _stop);
        tint = timer.current!.color;
      } else {
        title = 'Nothing is running';
      }
    } else if (projects.isEmpty) {
      title = 'No project matches “${cmd.query}”';
      detail = 'Projects are made on the web.';
      tint = p.inkMuted;
    } else {
      final best = projects.first;
      final same = best.id == timer.current?.id;
      tint = best.color;
      if (same && cmd.at == null) {
        title = '${best.name} is running';
        detail = 'Since ${formatTimeOfDay(timer.since!)}';
      } else {
        final q = previewStart(
          project: best.name,
          now: now,
          at: cmd.at,
          running: timer.current?.name,
          since: timer.since,
          same: same,
        );
        title = q.title;
        detail = q.detail;
        action = same ? 'Restart' : (timer.running ? 'Switch' : 'Start');
        run = () => _start(best);
      }
    }

    final problem = cmd.problem;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: (problem != null ? p.persimmon : tint).withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          if (problem == null) ...[ProjectDot(color: tint, size: 12), const SizedBox(width: 10)],
          Expanded(
            child: Text(problem ?? title,
                style: SkyType.display(18).copyWith(color: problem != null ? p.persimmonInk : p.ink)),
          ),
        ]),
        if (problem == null && detail != null) ...[
          const SizedBox(height: 6),
          Text(detail, style: SkyType.body(14).copyWith(color: p.inkOnSky)),
        ],
        if (action != null) ...[
          const SizedBox(height: 14),
          SizedBox(
            height: 52,
            child: SkyButton(
              label: action,
              kind: SkyButtonKind.primary,
              large: true,
              onPressed: problem == null ? run : null,
            ),
          ),
        ],
      ]),
    );
  }

  Widget _tiles(BuildContext context, List<Project> projects) {
    final p = context.sky;
    final timer = widget.timer;
    final worked = {for (final w in widget.week.weeks) w.project.id: w.worked};
    final best = _typed && _command.verb == QuickVerb.start ? projects.first.id : null;
    return LayoutBuilder(builder: (context, box) {
      const gap = 10.0;
      final width = (box.maxWidth - gap) / 2;
      return Wrap(spacing: gap, runSpacing: gap, children: [
        for (final project in projects.take(8))
          SizedBox(
            width: width,
            child: Builder(builder: (context) {
              final running = project.id == timer.current?.id;
              final ring = running || project.id == best;
              return Material(
                color: project.color.withValues(alpha: ring ? 0.2 : 0.1),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(22),
                  side: ring ? BorderSide(color: project.color, width: 2) : BorderSide.none,
                ),
                child: InkWell(
                  borderRadius: BorderRadius.circular(22),
                  onTap: running && !(_typed && _command.at != null) ? null : () => _start(project),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        ProjectDot(color: project.color),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(project.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: SkyType.body(15, weight: FontWeight.w700)),
                        ),
                      ]),
                      const SizedBox(height: 2),
                      Text(project.kindLabel, style: SkyType.body(12).copyWith(color: p.inkMuted)),
                      const SizedBox(height: 4),
                      running
                          ? ValueListenableBuilder(
                              valueListenable: timer.now,
                              builder: (context, _, _) => Text('Running · ${formatShortClock(timer.elapsed)}',
                                  style: SkyType.figure(14, weight: FontWeight.w700)),
                            )
                          : Text('${formatMinutes(((worked[project.id] ?? 0) * 60).round())} this week',
                              style: SkyType.figure(14, weight: FontWeight.w700)),
                    ]),
                  ),
                ),
              );
            }),
          ),
      ]);
    });
  }

  Widget _links(BuildContext context) {
    final p = context.sky;
    Widget link(IconData icon, String label, VoidCallback then) => ListTile(
          leading: Icon(icon, color: p.ink),
          title: Text(label, style: SkyType.body(15)),
          trailing: Icon(Icons.chevron_right_rounded, color: p.inkMuted),
          minTileHeight: 52,
          onTap: () {
            _close();
            then();
          },
        );
    return Container(
      decoration: BoxDecoration(color: p.wash, borderRadius: BorderRadius.circular(22)),
      clipBehavior: Clip.antiAlias,
      child: Material(
        type: MaterialType.transparency,
        child: Column(children: [
          link(Icons.history_rounded, 'Log time you forgot', widget.onLog),
          Divider(height: 1, color: p.hairline),
          link(Icons.dark_mode_outlined, 'Focus mode', widget.onFocus),
        ]),
      ),
    );
  }
}
