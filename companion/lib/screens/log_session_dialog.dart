import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/api_client.dart';
import '../services/date_keys.dart';
import '../services/past_session.dart';
import '../services/time_format.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';

/// "Log time you forgot to track": a project, today or yesterday, a from and
/// a to. One sentence says what will be logged, and an overlap with a
/// session already there is refused before anything is sent.
Future<void> showLogSession(
  BuildContext context, {
  required ApiClient client,
  required TimerController timer,
  WeekController? week,
}) async {
  final messenger = ScaffoldMessenger.of(context);
  final logged = await showDialog<String>(
    context: context,
    builder: (_) => _LogSessionDialog(client: client, timer: timer),
  );
  if (logged == null) return;
  messenger.showSnackBar(SnackBar(content: Text(logged)));
  await week?.refresh();
}

class _LogSessionDialog extends StatefulWidget {
  final ApiClient client;
  final TimerController timer;
  const _LogSessionDialog({required this.client, required this.timer});

  @override
  State<_LogSessionDialog> createState() => _LogSessionDialogState();
}

class _LogSessionDialogState extends State<_LogSessionDialog> {
  late Project? _project = widget.timer.recentFirst.firstOrNull;
  bool _yesterday = false;
  TimeOfDay _from = const TimeOfDay(hour: 9, minute: 0);
  TimeOfDay _to = const TimeOfDay(hour: 10, minute: 0);
  List<DaySpan> _existing = const [];
  bool _sending = false;
  String? _failure;

  DateTime get _day {
    final now = DateTime.now();
    return addDays(DateTime(now.year, now.month, now.day), _yesterday ? -1 : 0);
  }

  @override
  void initState() {
    super.initState();
    // Default to the hour that just ended, which is the usual "I forgot".
    final now = DateTime.now();
    _to = TimeOfDay(hour: now.hour, minute: 0);
    _from = TimeOfDay(hour: (now.hour + 23) % 24, minute: 0);
    _loadDay();
    widget.timer.addListener(_onProjects);
  }

  /// Opened before the projects were read (from the menu bar, at launch):
  /// take the most recent one once they arrive.
  void _onProjects() {
    if (_project == null && widget.timer.recentFirst.isNotEmpty) {
      setState(() => _project = widget.timer.recentFirst.first);
    }
  }

  @override
  void dispose() {
    widget.timer.removeListener(_onProjects);
    super.dispose();
  }

  /// The sessions already on the chosen day, to refuse an overlap here
  /// rather than after a round trip.
  Future<void> _loadDay() async {
    final day = _day;
    final next = addDays(day, 1);
    final utcDays = {
      DateTime.utc(day.toUtc().year, day.toUtc().month, day.toUtc().day),
      DateTime.utc(next.toUtc().year, next.toUtc().month, next.toUtc().day),
    };
    final spans = <DaySpan>[];
    for (final d in utcDays) {
      try {
        for (final b in await widget.client.getBeatsOn(d)) {
          final start = DateTime.tryParse(b['start'] as String? ?? '');
          if (start == null) continue;
          final end = DateTime.tryParse(b['end'] as String? ?? '');
          spans.add(DaySpan(start.toLocal(), end?.toLocal(),
              widget.timer.projectById(b['project_id'] as String?)?.name ?? 'another project'));
        }
      } catch (_) {
        // Without the day's sessions the server is the only check left.
      }
    }
    if (mounted) setState(() => _existing = spans);
  }

  (DateTime, DateTime) get _times => sessionTimes(_day, (_from.hour, _from.minute), (_to.hour, _to.minute));

  Future<void> _pick(bool from) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: from ? _from : _to,
      helpText: from ? 'Started at' : 'Finished at',
    );
    if (picked == null) return;
    setState(() {
      if (from) {
        _from = picked;
      } else {
        _to = picked;
      }
      _failure = null;
    });
  }

  Future<void> _send() async {
    final project = _project;
    if (project == null) return;
    final (start, end) = _times;
    setState(() {
      _sending = true;
      _failure = null;
    });
    try {
      await widget.client.createBeat(projectId: project.id, start: start, end: end);
      if (!mounted) return;
      Navigator.of(context).pop('${formatDuration(end.difference(start))} logged to ${project.name}, '
          '${formatTimeOfDay(start)}–${formatTimeOfDay(end)}');
    } catch (e) {
      if (mounted) {
        setState(() {
          _sending = false;
          _failure = 'Couldn\'t log it: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final projects = widget.timer.recentFirst;
    final (start, end) = _times;
    final problem = pastSessionProblem(start, end, DateTime.now(), existing: _existing);
    final project = _project;

    Widget timeButton(String label, TimeOfDay t, bool from) => Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: SkyType.body(12, weight: FontWeight.w700).copyWith(color: p.inkMuted)),
            const SizedBox(height: 6),
            SizedBox(
              width: double.infinity,
              child: SkyButton(
                label: '${t.hour}:${t.minute.toString().padLeft(2, '0')}',
                large: true,
                onPressed: () => _pick(from),
              ),
            ),
          ]),
        );

    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(28, 26, 28, 20),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('Log time you forgot', style: SkyType.display(22)),
            const SizedBox(height: 18),
            Text('Project', style: SkyType.body(12, weight: FontWeight.w700).copyWith(color: p.inkMuted)),
            const SizedBox(height: 6),
            // Keyed by id: the timer rebuilds its Project objects on every poll.
            DropdownButtonFormField<String>(
              key: ValueKey(project?.id),
              initialValue: project?.id,
              isExpanded: true,
              borderRadius: BorderRadius.circular(16),
              items: [
                for (final pr in projects)
                  DropdownMenuItem(
                    value: pr.id,
                    child: Row(children: [
                      ProjectDot(color: pr.color),
                      const SizedBox(width: 10),
                      Flexible(child: Text(pr.name, overflow: TextOverflow.ellipsis)),
                    ]),
                  ),
              ],
              onChanged: (id) => setState(() => _project = widget.timer.projectById(id)),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: SegmentedPills<bool>(
                options: const [(false, 'Today'), (true, 'Yesterday')],
                value: _yesterday,
                onChanged: (v) {
                  setState(() => _yesterday = v);
                  _loadDay();
                },
              ),
            ),
            const SizedBox(height: 16),
            Row(children: [
              timeButton('From', _from, true),
              const SizedBox(width: 12),
              timeButton('To', _to, false),
            ]),
            const SizedBox(height: 16),
            Text(
              problem ??
                  _failure ??
                  (project == null
                      ? 'Pick a project.'
                      : 'Logs ${formatDuration(end.difference(start))} to ${project.name}, '
                          '${DateFormat('EEEE').format(start)} ${formatTimeOfDay(start)}–${formatTimeOfDay(end)}.'),
              style: SkyType.body(14).copyWith(
                color: problem != null || _failure != null ? p.persimmonInk : p.inkOnSky,
              ),
            ),
            const SizedBox(height: 18),
            Row(mainAxisAlignment: MainAxisAlignment.end, children: [
              SkyButton(label: 'Cancel', onPressed: () => Navigator.of(context).pop()),
              const SizedBox(width: 10),
              SkyButton(
                label: _sending ? 'Logging…' : 'Log it',
                kind: SkyButtonKind.primary,
                onPressed: problem == null && project != null && !_sending ? _send : null,
              ),
            ]),
          ]),
        ),
      ),
    );
  }
}
