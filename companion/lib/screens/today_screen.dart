import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/api_client.dart';
import '../services/body_story.dart';
import '../services/date_keys.dart';
import '../services/day_ribbon.dart';
import '../services/time_format.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'timer_actions.dart';

/// Today: the timer, the day on one line, and the week, the coach and the
/// body in a sentence each.
class TodayScreen extends StatefulWidget {
  final ApiClient client;
  final TimerController timer;
  final WeekController week;
  final VoidCallback onOpenFlow;
  final VoidCallback onOpenCoach;
  final VoidCallback onOpenBody;
  final VoidCallback? onFind;

  const TodayScreen({
    super.key,
    required this.client,
    required this.timer,
    required this.week,
    required this.onOpenFlow,
    required this.onOpenCoach,
    required this.onOpenBody,
    this.onFind,
  });

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  List<Map<String, dynamic>> _beats = const [];
  List<Map<String, dynamic>> _flow = const [];
  List<Map<String, dynamic>> _events = const [];
  Map<String, dynamic>? _brief;
  BodyWeek _body = const BodyWeek([]);
  Map<String, dynamic>? _suggestion;
  final _dismissed = <String>{};
  Timer? _poll;
  String _timerKey = '';

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(minutes: 1), (_) => _load());
    widget.timer.addListener(_onTimer);
  }

  @override
  void dispose() {
    _poll?.cancel();
    widget.timer.removeListener(_onTimer);
    super.dispose();
  }

  void _onTimer() {
    final key = '${widget.timer.current?.id}@${widget.timer.since}';
    if (key != _timerKey) {
      _timerKey = key;
      _load();
    }
  }

  Future<T?> _try<T>(Future<T> f) async {
    try {
      return await f;
    } catch (_) {
      return null;
    }
  }

  Future<void> _load() async {
    final now = DateTime.now();
    final dayStart = DateTime(now.year, now.month, now.day);
    final dayEnd = addDays(dayStart, 1);
    // The API files sessions under their UTC start date; a local day can
    // touch two of them.
    final utcDays = {
      DateTime.utc(dayStart.toUtc().year, dayStart.toUtc().month, dayStart.toUtc().day),
      DateTime.utc(now.toUtc().year, now.toUtc().month, now.toUtc().day),
    };
    final results = await Future.wait([
      Future.wait(utcDays.map((d) => _try(widget.client.getBeatsOn(d)))),
      _try(widget.client.getFlowWindows(dayStart.toUtc().toIso8601String(), now.toUtc().toIso8601String())),
      _try(widget.client.getCalendarEvents(dayStart, dayEnd)),
      _try(widget.client.getTodayBrief()),
      _try(widget.client.getBiometrics(dayKey(addDays(dayStart, -1)), dayKey(dayStart))),
      _try(widget.client.getPendingSuggestions(since: now.subtract(const Duration(minutes: 30)))),
    ]);
    if (!mounted) return;
    final beats = [
      for (final list in results[0] as List<List<Map<String, dynamic>>?>) ...?list,
    ].where((b) {
      final start = DateTime.tryParse(b['start'] as String? ?? '')?.toLocal();
      return start != null && !start.isBefore(dayStart) && start.isBefore(dayEnd);
    }).toList();
    final suggestions = (results[5] as List<Map<String, dynamic>>?) ?? const [];
    setState(() {
      _beats = beats;
      _flow = (results[1] as List<Map<String, dynamic>>?) ?? const [];
      _events = ((results[2] as List<Map<String, dynamic>>?) ?? const [])
          .where((e) => e['all_day'] != true)
          .toList();
      _brief = results[3] as Map<String, dynamic>?;
      _body = BodyWeek((results[4] as List<Map<String, dynamic>>?) ?? const []);
      _suggestion = suggestions.where((s) => !_dismissed.contains(s['id'])).firstOrNull;
    });
  }

  /// The average flow score over the last 20 minutes, or null without data.
  int? get _recentFlow {
    final cutoff = DateTime.now().toUtc().subtract(const Duration(minutes: 20));
    final scores = [
      for (final w in _flow)
        if ((DateTime.tryParse(w['window_start'] as String? ?? '')?.isAfter(cutoff) ?? false) &&
            w['flow_score'] is num)
          (w['flow_score'] as num).toDouble(),
    ];
    if (scores.isEmpty) return null;
    return (scores.reduce((a, b) => a + b) / scores.length * 100).round();
  }

  String _greeting(DateTime now) {
    if (now.hour < 5) return 'Still up';
    if (now.hour < 12) return 'Good morning';
    if (now.hour < 18) return 'Good afternoon';
    return 'Good evening';
  }

  Future<void> _pickProject() async {
    final timer = widget.timer;
    final picked = await showDialog<Project>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text('Switch to', style: SkyType.display(20)),
        children: [
          for (final p in timer.recentFirst.where((p) => p.id != timer.current?.id))
            SimpleDialogOption(
              onPressed: () => Navigator.pop(ctx, p),
              child: Row(children: [
                ProjectDot(color: p.color),
                const SizedBox(width: 12),
                Text(p.name, style: SkyType.body(15)),
              ]),
            ),
        ],
      ),
    );
    if (picked != null && mounted) await TimerActions.start(context, timer, picked);
  }

  Future<void> _startedEarlier() async {
    final since = widget.timer.since?.toLocal();
    if (since == null) return;
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(since),
      helpText: 'When did you start?',
    );
    if (picked == null || !mounted) return;
    final start = DateTime(since.year, since.month, since.day, picked.hour, picked.minute);
    final messenger = ScaffoldMessenger.of(context);
    if (start.isAfter(DateTime.now())) {
      messenger.showSnackBar(const SnackBar(content: Text('That time hasn\'t happened yet.')));
      return;
    }
    try {
      await widget.timer.moveStart(start);
      messenger.showSnackBar(SnackBar(content: Text('Started at ${formatTimeOfDay(start)}')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Couldn\'t change the start: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final now = DateTime.now();
    return ListenableBuilder(
      listenable: Listenable.merge([widget.timer, widget.week]),
      builder: (context, _) => ListView(
        padding: const EdgeInsets.fromLTRB(32, 36, 32, 40),
        children: [
          _Column(children: [
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(DateFormat('EEEE, d MMMM').format(now),
                      style: SkyType.body(14).copyWith(color: p.inkOnSky)),
                  const SizedBox(height: 2),
                  Semantics(header: true, child: Text(_greeting(now), style: SkyType.display(34))),
                ]),
              ),
              if (widget.onFind != null) _FindButton(onPressed: widget.onFind!),
            ]),
            if (_suggestion != null && _suggestion!['project_id'] != widget.timer.current?.id) ...[
              const SizedBox(height: 18),
              _SuggestionBanner(
                suggestion: _suggestion!,
                project: widget.timer.projectById(_suggestion!['project_id'] as String?),
                running: widget.timer.running,
                onAccept: (project) => TimerActions.start(context, widget.timer, project),
                onDismiss: () => setState(() {
                  _dismissed.add(_suggestion!['id'] as String? ?? '');
                  _suggestion = null;
                }),
              ),
            ],
            const SizedBox(height: 18),
            _hero(context),
            const SizedBox(height: 18),
            _ribbon(context),
            const SizedBox(height: 18),
            _cards(context),
          ]),
        ],
      ),
    );
  }

  Widget _hero(BuildContext context) {
    final timer = widget.timer;
    final ring = ValueListenableBuilder(
      valueListenable: timer.now,
      builder: (context, now, _) {
        final today = widget.week.todayMinutes(now);
        final target = widget.week.dailyTargetMinutes(now);
        final p = context.sky;
        return Column(mainAxisSize: MainAxisSize.min, children: [
          ProgressRing(
            fraction: target == null || target == 0 ? 0 : today / target,
            color: p.sun,
            semanticsLabel: target == null
                ? '${formatMinutes(today)} tracked today'
                : '${formatMinutes(today)} of ${formatMinutes(target)} tracked today',
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(formatMinutes(today), style: SkyType.figure(28)),
              const SizedBox(height: 6),
              Text(target == null ? 'today' : 'of ${formatMinutes(target)}',
                  style: SkyType.body(13).copyWith(color: p.inkMuted)),
            ]),
          ),
          const SizedBox(height: 8),
          Text('Today, all projects', style: SkyType.body(13).copyWith(color: p.inkMuted)),
        ]);
      },
    );
    return Panel(
      raised: true,
      padding: const EdgeInsets.fromLTRB(32, 28, 32, 28),
      child: LayoutBuilder(builder: (context, box) {
        final body = timer.running ? _running(context) : _idle(context);
        if (box.maxWidth < 620) {
          return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            body,
            const SizedBox(height: 24),
            Center(child: ring),
          ]);
        }
        return Row(children: [Expanded(child: body), const SizedBox(width: 28), ring]);
      }),
    );
  }

  Widget _running(BuildContext context) {
    final p = context.sky;
    final timer = widget.timer;
    final project = timer.current!;
    final flow = _recentFlow;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 10, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Container(
          padding: const EdgeInsets.fromLTRB(10, 6, 14, 6),
          decoration: BoxDecoration(
            color: project.color.withValues(alpha: 0.16),
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            ProjectDot(color: project.color),
            const SizedBox(width: 8),
            Text(project.name, style: SkyType.body(14, weight: FontWeight.w700)),
          ]),
        ),
        Text('${project.kindLabel} · since ${formatTimeOfDay(timer.since!)}',
            style: SkyType.body(13).copyWith(color: p.inkMuted)),
      ]),
      const SizedBox(height: 12),
      ValueListenableBuilder(
        valueListenable: timer.now,
        builder: (context, _, _) => Semantics(
          label: 'Running for ${formatDuration(timer.elapsed)}',
          excludeSemantics: true,
          child: FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(formatClock(timer.elapsed), style: SkyType.figure(84).copyWith(letterSpacing: -1)),
          ),
        ),
      ),
      if (flow != null) ...[
        const SizedBox(height: 12),
        Row(children: [
          Icon(Icons.show_chart_rounded, size: 18, color: flow >= 70 ? p.leaf : p.inkMuted),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              flow >= 70
                  ? 'Flow $flow over the last 20 minutes — you\'re in it.'
                  : 'Flow $flow over the last 20 minutes.',
              style: SkyType.body(14).copyWith(color: p.inkOnSky),
            ),
          ),
        ]),
      ],
      const SizedBox(height: 18),
      Wrap(spacing: 10, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
        SkyButton(
          label: 'Stop',
          icon: Icons.stop_rounded,
          shortcut: '⌘.',
          kind: SkyButtonKind.primary,
          large: true,
          onPressed: () => TimerActions.stop(context, timer),
        ),
        SkyButton(label: 'Switch project', large: true, onPressed: _pickProject),
        LinkButton(label: 'Started earlier?', onPressed: _startedEarlier),
      ]),
    ]);
  }

  Widget _idle(BuildContext context) {
    final p = context.sky;
    final timer = widget.timer;
    final stopped = timer.lastStopped;
    final fresh = stopped != null && DateTime.now().difference(stopped.at) < const Duration(minutes: 10);
    final projects = timer.recentFirst.take(5).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (fresh) ...[
        Container(
          padding: const EdgeInsets.fromLTRB(14, 4, 4, 4),
          decoration: BoxDecoration(
            color: p.leaf.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(children: [
            Icon(Icons.check_rounded, size: 18, color: p.leafInk),
            const SizedBox(width: 10),
            Expanded(
              child: Text('${formatDuration(stopped.length)} logged to ${stopped.project.name}',
                  style: SkyType.body(14).copyWith(color: p.leafInk)),
            ),
            LinkButton(
              label: 'Undo',
              bold: true,
              color: p.leafInk,
              onPressed: () => TimerActions.undo(ScaffoldMessenger.of(context), timer),
            ),
          ]),
        ),
        const SizedBox(height: 16),
      ],
      Text('What\'s next?', style: SkyType.display(40)),
      const SizedBox(height: 16),
      if (projects.isEmpty)
        Text('Create a project on the web to start tracking.',
            style: SkyType.body(15).copyWith(color: p.inkMuted))
      else
        Wrap(spacing: 10, runSpacing: 10, children: [
          for (final project in projects)
            FilledButton(
              onPressed: () => TimerActions.start(context, timer, project),
              style: FilledButton.styleFrom(
                backgroundColor: project.color.withValues(alpha: 0.16),
                foregroundColor: p.ink,
                shape: const StadiumBorder(),
                minimumSize: const Size(0, 48),
                padding: const EdgeInsets.fromLTRB(14, 0, 18, 0),
                textStyle: SkyType.body(15, weight: FontWeight.w700),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.play_arrow_rounded, color: project.color, size: 20),
                const SizedBox(width: 6),
                Text(project.name),
              ]),
            ),
        ]),
    ]);
  }

  Widget _ribbon(BuildContext context) {
    final p = context.sky;
    final now = DateTime.now();
    DateTime? parse(Object? s) => s is String ? DateTime.tryParse(s)?.toLocal() : null;
    final sessions = [
      for (final b in _beats)
        if (parse(b['start']) != null)
          (parse(b['start'])!, parse(b['end']), widget.timer.projectById(b['project_id'] as String?)),
    ];
    final events = [
      for (final e in _events)
        if (parse(e['start']) != null && parse(e['end']) != null)
          (parse(e['start'])!, parse(e['end']), e['summary'] as String? ?? ''),
    ];
    final window = dayWindowFor(now, [
      now,
      for (final s in sessions) ...[s.$1, ?s.$2],
      for (final e in events) ...[e.$1, ?e.$2],
    ]);
    final flow = flowBuckets(window, [
      for (final w in _flow)
        if (parse(w['window_start']) != null && w['flow_score'] is num)
          (parse(w['window_start'])!, (w['flow_score'] as num).toDouble()),
    ]);
    final placedSessions = placeSpans(window, sessions, now: now);
    final placedEvents = placeSpans(window, events, now: now);
    final nowAt = window.fractionOf(now);

    Widget label(String text) => SizedBox(
          width: 74,
          child: Text(text, style: SkyType.body(12).copyWith(color: p.inkMuted)),
        );

    return Panel(
      padding: const EdgeInsets.fromLTRB(26, 22, 26, 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: PanelHeading('Your day', subtitle: 'Sessions, flow and calendar on one line'),
          ),
          LinkButton(label: 'Open Flow', bold: true, color: p.sunInk, onPressed: widget.onOpenFlow),
        ]),
        const SizedBox(height: 16),
        if (flow.any((f) => f != null)) ...[
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            label('Flow'),
            Expanded(
              child: SizedBox(
                height: 40,
                child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  for (final f in flow)
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 1),
                        child: Container(
                          height: f == null ? 3 : (f * 40).clamp(3, 40).toDouble(),
                          decoration: BoxDecoration(
                            color: _flowColor(p, f),
                            borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                          ),
                        ),
                      ),
                    ),
                ]),
              ),
            ),
          ]),
          const SizedBox(height: 10),
        ],
        Row(children: [
          label('Tracked'),
          Expanded(
            child: LayoutBuilder(builder: (context, box) {
              final w = box.maxWidth;
              return SizedBox(
                height: 34,
                child: Stack(clipBehavior: Clip.none, children: [
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(color: p.wash, borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                  for (final s in placedSessions)
                    Positioned(
                      left: w * s.left,
                      width: (w * s.width).clamp(3, w).toDouble(),
                      top: 3,
                      bottom: 3,
                      child: Tooltip(
                        message: s.item?.name ?? 'Session',
                        child: Container(
                          alignment: Alignment.centerLeft,
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          decoration: BoxDecoration(
                            color: s.item?.color ?? p.inkMuted,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: w * s.width > 70
                              ? Text(s.item?.name ?? '',
                                  maxLines: 1,
                                  overflow: TextOverflow.clip,
                                  style: SkyType.body(12, weight: FontWeight.w700).copyWith(color: Colors.white))
                              : null,
                        ),
                      ),
                    ),
                  Positioned(
                    left: w * nowAt - 1,
                    top: -6,
                    bottom: -6,
                    width: 2,
                    child: DecoratedBox(
                      decoration: BoxDecoration(color: p.ink, borderRadius: BorderRadius.circular(2)),
                    ),
                  ),
                ]),
              );
            }),
          ),
        ]),
        if (placedEvents.isNotEmpty) ...[
          const SizedBox(height: 10),
          Row(children: [
            label('Calendar'),
            Expanded(
              child: LayoutBuilder(builder: (context, box) {
                final w = box.maxWidth;
                return SizedBox(
                  height: 26,
                  child: Stack(children: [
                    for (final e in placedEvents)
                      Positioned(
                        left: w * e.left,
                        width: (w * e.width).clamp(3, w).toDouble(),
                        top: 0,
                        bottom: 0,
                        child: Tooltip(
                          message: e.item,
                          child: Container(
                            alignment: Alignment.centerLeft,
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: p.ink.withValues(alpha: 0.28), width: 1.5),
                            ),
                            child: Text(e.item,
                                maxLines: 1,
                                overflow: TextOverflow.clip,
                                style: SkyType.body(12).copyWith(color: p.inkOnSky)),
                          ),
                        ),
                      ),
                  ]),
                );
              }),
            ),
          ]),
        ],
        const SizedBox(height: 8),
        Row(children: [
          const SizedBox(width: 74),
          Expanded(
            child: LayoutBuilder(builder: (context, box) {
              final ticks = window.hourTicks(step: window.length.inHours > 14 ? 3 : 2);
              return SizedBox(
                height: 16,
                child: Stack(children: [
                  for (final h in ticks)
                    Positioned(
                      left: (box.maxWidth *
                                  window.fractionOf(DateTime(window.start.year, window.start.month,
                                      window.start.day, h)) -
                              8)
                          .clamp(0, box.maxWidth - 16)
                          .toDouble(),
                      child: Text('$h', style: SkyType.figure(11, weight: FontWeight.w500).copyWith(color: p.inkMuted)),
                    ),
                ]),
              );
            }),
          ),
        ]),
        if (placedSessions.isEmpty && !flow.any((f) => f != null))
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text('Nothing tracked yet today.', style: SkyType.body(13).copyWith(color: p.inkMuted)),
          ),
      ]),
    );
  }

  Color _flowColor(SkyPalette p, double? f) {
    if (f == null) return p.wash;
    if (f >= 0.7) return p.leaf;
    if (f >= 0.45) return p.hills[1];
    return p.hills[0];
  }

  Widget _cards(BuildContext context) {
    final cards = [_weekCard(context), _coachCard(context), _bodyCard(context)];
    return LayoutBuilder(builder: (context, box) {
      final cols = box.maxWidth >= 840 ? 3 : (box.maxWidth >= 560 ? 2 : 1);
      const gap = 18.0;
      final width = (box.maxWidth - gap * (cols - 1)) / cols;
      return Wrap(spacing: gap, runSpacing: gap, children: [
        for (final c in cards) SizedBox(width: width, height: 248, child: c),
      ]);
    });
  }

  Widget _weekCard(BuildContext context) {
    final p = context.sky;
    final week = widget.week;
    final anchor = week.anchor;
    final todayIndex = DateTime.now().weekday - 1;
    final worked = anchor?.worked ?? week.weeks.fold<double>(0, (a, w) => a + w.worked);
    final days = anchor?.days ??
        List.generate(7, (i) => week.weeks.fold<double>(0, (a, w) => a + w.days[i]));
    final maxDay = days.fold<double>(1, (a, b) => b > a ? b : a);
    return Panel(
      padding: const EdgeInsets.fromLTRB(24, 22, 24, 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const PanelHeading('This week', size: 17),
        const SizedBox(height: 12),
        Wrap(crossAxisAlignment: WrapCrossAlignment.end, spacing: 8, children: [
          Text(formatMinutes((worked * 60).round()), style: SkyType.figure(30)),
          if (anchor != null)
            Text('of ${formatMinutes((anchor.target! * 60).round())} at ${anchor.project.name}',
                style: SkyType.body(13).copyWith(color: p.inkMuted)),
        ]),
        const SizedBox(height: 14),
        Expanded(
          child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            for (var i = 0; i < 7; i++)
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                    Flexible(
                      child: FractionallySizedBox(
                        heightFactor: (days[i] / maxDay).clamp(0.06, 1.0),
                        child: Container(
                          decoration: BoxDecoration(
                            color: i == todayIndex
                                ? p.sun
                                : days[i] > 0
                                    ? p.washStrong
                                    : p.wash,
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(const ['M', 'T', 'W', 'T', 'F', 'S', 'S'][i],
                        style: SkyType.body(11, weight: i == todayIndex ? FontWeight.w700 : FontWeight.w400)
                            .copyWith(color: i == todayIndex ? p.ink : p.inkMuted)),
                  ]),
                ),
              ),
          ]),
        ),
        const SizedBox(height: 12),
        if (anchor?.balance != null)
          Chip2(
            '${formatBalance(anchor!.balance!)} ${anchor.balance! >= 0 ? 'ahead' : 'behind'} overall',
            bold: true,
            background: (anchor.balance! >= 0 ? p.leaf : p.persimmon).withValues(alpha: 0.14),
            foreground: anchor.balance! >= 0 ? p.leafInk : p.persimmonInk,
          )
        else if (anchor == null)
          Text('Set a weekly goal on the web to see your pace.',
              style: SkyType.body(12).copyWith(color: p.inkMuted)),
      ]),
    );
  }

  Widget _coachCard(BuildContext context) {
    final p = context.sky;
    final created = DateTime.tryParse(_brief?['created_at'] as String? ?? '');
    final excerpt = briefExcerpt(_brief?['body'] as String?);
    return Panel(
      padding: const EdgeInsets.fromLTRB(24, 22, 24, 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(child: PanelHeading('From your coach', size: 17)),
          if (created != null)
            Text(formatTimeOfDay(created), style: SkyType.body(12).copyWith(color: p.inkMuted)),
        ]),
        const SizedBox(height: 10),
        Expanded(
          child: Text(
            excerpt ?? 'No brief yet today. Your coach writes one each morning.',
            overflow: TextOverflow.fade,
            style: SkyType.body(15, height: 1.7).copyWith(color: excerpt == null ? p.inkMuted : p.ink),
          ),
        ),
        LinkButton(label: 'Read the full brief', bold: true, color: p.sunInk, onPressed: widget.onOpenCoach),
      ]),
    );
  }

  Widget _bodyCard(BuildContext context) {
    final p = context.sky;
    final readiness = _body.latest('readiness_score');
    final sleep = _body.latest('sleep_minutes');
    final hrv = _body.latest('hrv_ms');
    final rhr = _body.latest('resting_hr_bpm');
    return Panel(
      padding: const EdgeInsets.fromLTRB(24, 22, 24, 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(child: PanelHeading('Body', size: 17)),
          if (_body.sources != null) Text(_body.sources!, style: SkyType.body(12).copyWith(color: p.inkMuted)),
        ]),
        const SizedBox(height: 12),
        if (_body.isEmpty)
          Expanded(
            child: Text('No health data yet. Connect Oura or Fitbit in Settings.',
                style: SkyType.body(14).copyWith(color: p.inkMuted)),
          )
        else ...[
          if (readiness != null)
            Row(children: [
              Container(
                width: 56,
                height: 56,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: p.leaf.withValues(alpha: 0.14), shape: BoxShape.circle),
                child: Text('${readiness.round()}', style: SkyType.figure(22).copyWith(color: p.leafInk)),
              ),
              const SizedBox(width: 14),
              Expanded(child: Text(readinessLine(readiness.round()), style: SkyType.body(14))),
            ]),
          const Spacer(),
          Row(children: [
            for (final (value, label) in [
              (sleep == null ? '—' : formatSleep(sleep), 'Sleep'),
              (hrv == null ? '—' : '${hrv.round()} ms', 'HRV'),
              (rhr == null ? '—' : '${rhr.round()}', 'Resting HR'),
            ])
              Expanded(
                child: Container(
                  margin: const EdgeInsets.only(right: 6),
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  decoration: BoxDecoration(color: p.wash, borderRadius: BorderRadius.circular(14)),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    FittedBox(child: Text(value, style: SkyType.figure(15, weight: FontWeight.w700))),
                    const SizedBox(height: 4),
                    Text(label, maxLines: 1, style: SkyType.body(11).copyWith(color: p.inkMuted)),
                  ]),
                ),
              ),
          ]),
        ],
        LinkButton(label: 'Open Body', bold: true, color: p.sunInk, onPressed: widget.onOpenBody),
      ]),
    );
  }
}

/// Keeps a screen's content to a readable width on a wide window.
class _Column extends StatelessWidget {
  final List<Widget> children;
  const _Column({required this.children});

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1040),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
        ),
      );
}

class _FindButton extends StatelessWidget {
  final VoidCallback onPressed;
  const _FindButton({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Material(
      color: p.panel,
      shape: const StadiumBorder(),
      child: InkWell(
        onTap: onPressed,
        customBorder: const StadiumBorder(),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.search_rounded, size: 18, color: p.inkMuted),
            const SizedBox(width: 8),
            Text('Start or find anything', style: SkyType.body(14).copyWith(color: p.inkMuted)),
            const SizedBox(width: 10),
            const Chip2('⌘K'),
          ]),
        ),
      ),
    );
  }
}

class _SuggestionBanner extends StatelessWidget {
  final Map<String, dynamic> suggestion;
  final Project? project;
  final bool running;
  final ValueChanged<Project> onAccept;
  final VoidCallback onDismiss;

  const _SuggestionBanner({
    required this.suggestion,
    required this.project,
    required this.running,
    required this.onAccept,
    required this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final project = this.project;
    if (project == null) return const SizedBox.shrink();
    final repo = suggestion['editor_repo'] as String?;
    return Panel(
      radius: 20,
      padding: const EdgeInsets.fromLTRB(18, 10, 12, 10),
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 14,
        runSpacing: 8,
        children: [
          ProjectDot(color: project.color),
          Text.rich(
            TextSpan(children: [
              if (repo != null) ...[
                const TextSpan(text: 'Your editor is on '),
                TextSpan(text: repo, style: const TextStyle(fontWeight: FontWeight.w700)),
                const TextSpan(text: '. '),
              ],
              const TextSpan(text: 'Track it as '),
              TextSpan(text: project.name, style: const TextStyle(fontWeight: FontWeight.w700)),
              const TextSpan(text: '?'),
            ]),
            style: SkyType.body(14).copyWith(color: p.ink),
          ),
          SkyButton(
            label: running ? 'Switch to ${project.name}' : 'Start ${project.name}',
            kind: SkyButtonKind.dark,
            onPressed: () {
              onDismiss();
              onAccept(project);
            },
          ),
          SkyButton(label: 'Not now', onPressed: onDismiss),
        ],
      ),
    );
  }
}
