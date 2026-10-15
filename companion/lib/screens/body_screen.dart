import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/api_client.dart';
import '../services/body_story.dart';
import '../services/date_keys.dart';
import '../services/flow_summary.dart';
import '../services/time_format.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';

/// Body: readiness in a sentence, the week's sleep, HRV, resting heart rate
/// and steps, and how each night's sleep lined up with the next day's flow.
class BodyScreen extends StatefulWidget {
  final ApiClient client;
  const BodyScreen({super.key, required this.client});

  @override
  State<BodyScreen> createState() => _BodyScreenState();
}

class _BodyScreenState extends State<BodyScreen> {
  bool _loading = true;
  BodyWeek _week = const BodyWeek([]);
  List<SleepFlowPair> _pairs = const [];
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(minutes: 10), (_) => _load());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  /// The last seven local days, oldest first, ending today.
  List<DateTime> get _days {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return [for (var i = 6; i >= 0; i--) addDays(today, -i)];
  }

  Future<void> _load() async {
    final days = _days;
    BodyWeek week;
    try {
      week = BodyWeek(await widget.client.getBiometrics(dayKey(days.first), dayKey(days.last)));
    } catch (_) {
      week = const BodyWeek([]);
    }
    final flows = await Future.wait(days.map((d) async {
      try {
        final summary = await widget.client.getFlowWindowsSummary(
          d.toUtc().toIso8601String(),
          addDays(d, 1).toUtc().toIso8601String(),
        );
        return parseFlowSummary(summary)?.avg;
      } catch (_) {
        return null;
      }
    }));
    final flowByDate = <String, int>{
      for (var i = 0; i < days.length; i++)
        if (flows[i] != null) dayKey(days[i]): flows[i]!,
    };
    if (!mounted) return;
    setState(() {
      _week = week;
      _pairs = pairSleepWithFlow(week, flowByDate, days);
      _loading = false;
    });
  }

  String? _syncedLabel() {
    final sources = _week.sources;
    final synced = _week.lastSynced?.toLocal();
    if (sources == null) return null;
    if (synced == null) return sources;
    final now = DateTime.now();
    final sameDay = synced.year == now.year && synced.month == now.month && synced.day == now.day;
    return sameDay
        ? '$sources, synced ${formatTimeOfDay(synced)}'
        : '$sources, synced ${DateFormat('d MMM').format(synced)}';
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final synced = _syncedLabel();
    return ListView(
      padding: pagePadding(context),
      children: [
        _Column(children: [
          Row(children: [
            Expanded(child: Semantics(header: true, child: Text('Body', style: SkyType.display(isCompact(context) ? 30 : 34)))),
            if (synced != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(color: p.panel, borderRadius: BorderRadius.circular(999)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  ProjectDot(color: p.leaf, size: 8),
                  const SizedBox(width: 8),
                  Text(synced, style: SkyType.body(13)),
                ]),
              ),
          ]),
          const SizedBox(height: 18),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 80),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_week.isEmpty)
            Panel(
              child: EmptyNote(
                icon: Icons.favorite_border_rounded,
                title: 'No health data yet',
                body: 'Connect Oura or Fitbit in Settings${Platform.isMacOS ? ' (⌘,)' : ''} and your sleep, '
                    'HRV and readiness show up here.',
              ),
            )
          else ...[
            _readiness(context),
            const SizedBox(height: 18),
            _metrics(context),
            const SizedBox(height: 18),
            _sleepAndFlow(context),
          ],
        ]),
      ],
    );
  }

  Widget _readiness(BuildContext context) {
    final p = context.sky;
    final score = _week.latest('readiness_score')?.round();
    final recovery = recoveryLine(_week);
    final text = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(
        score != null ? readinessLine(score) : 'Your last seven days',
        style: SkyType.display(24, weight: FontWeight.w700).copyWith(height: 1.4),
      ),
      if (recovery != null) ...[
        const SizedBox(height: 8),
        Text(recovery, style: SkyType.body(15, height: 1.7).copyWith(color: p.inkOnSky)),
      ],
    ]);
    return Panel(
      raised: true,
      padding: const EdgeInsets.fromLTRB(32, 28, 32, 28),
      child: score == null
          ? text
          : LayoutBuilder(builder: (context, box) {
              final ring = ProgressRing(
                fraction: score / 100,
                color: p.leaf,
                size: 150,
                stroke: 13,
                semanticsLabel: 'Readiness $score of 100',
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text('$score', style: SkyType.figure(42)),
                  const SizedBox(height: 4),
                  Text('readiness', style: SkyType.body(13).copyWith(color: p.inkMuted)),
                ]),
              );
              if (box.maxWidth < 560) {
                return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Center(child: ring),
                  const SizedBox(height: 20),
                  text,
                ]);
              }
              return Row(children: [ring, const SizedBox(width: 36), Expanded(child: text)]);
            }),
    );
  }

  Widget _metrics(BuildContext context) {
    final p = context.sky;
    final sleep = _week.latest('sleep_minutes');
    final hrv = _week.latest('hrv_ms');
    final rhr = _week.latest('resting_hr_bpm');
    final steps = _week.latest('steps');
    final tiles = [
      _MetricTile(
        name: 'Sleep',
        value: sleep == null ? '—' : formatSleep(sleep),
        series: _week.series('sleep_minutes'),
        color: _sleepColor,
        note: metricNote(_week, 'sleep_minutes'),
      ),
      _MetricTile(
        name: 'HRV',
        value: hrv == null ? '—' : '${hrv.round()} ms',
        series: _week.series('hrv_ms'),
        color: p.leaf,
        note: metricNote(_week, 'hrv_ms'),
      ),
      _MetricTile(
        name: 'Resting heart rate',
        value: rhr == null ? '—' : '${rhr.round()} bpm',
        series: _week.series('resting_hr_bpm'),
        color: p.persimmon,
        note: metricNote(_week, 'resting_hr_bpm'),
      ),
      _MetricTile(
        name: 'Steps',
        value: steps == null ? '—' : formatSteps(steps),
        series: _week.series('steps'),
        color: p.sunInk,
        note: metricNote(_week, 'steps'),
      ),
    ];
    return LayoutBuilder(builder: (context, box) {
      final cols = box.maxWidth >= 840 ? 4 : (box.maxWidth >= 480 ? 2 : 1);
      const gap = 18.0;
      final width = (box.maxWidth - gap * (cols - 1)) / cols;
      return Wrap(spacing: gap, runSpacing: gap, children: [
        for (final t in tiles) SizedBox(width: width, child: t),
      ]);
    });
  }

  Widget _sleepAndFlow(BuildContext context) {
    final p = context.sky;
    final line = sleepFlowLine(_pairs);
    final hasAny = _pairs.any((x) => x.sleepHours != null || x.flow != null);
    Widget legend(Color c, String label) => Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 6),
          Text(label, style: SkyType.body(13)),
        ]);
    const barMax = 116.0;
    return Panel(
      padding: const EdgeInsets.fromLTRB(26, 22, 26, 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(
          spacing: 16,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            const PanelHeading('Sleep, then flow'),
            legend(_sleepColor, 'Sleep the night before'),
            legend(p.leaf, 'Average flow'),
          ],
        ),
        const SizedBox(height: 8),
        if (line != null)
          Text(line, style: SkyType.body(15).copyWith(color: p.inkOnSky))
        else
          Text(
            'Once there are nights over seven hours and under six, each followed by a tracked day, '
            'this compares them.',
            style: SkyType.body(14).copyWith(color: p.inkMuted),
          ),
        const SizedBox(height: 16),
        if (hasAny)
          SizedBox(
            height: barMax + 26,
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              for (final pair in _pairs)
                Expanded(
                  child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        _Bar(
                          height: pair.sleepHours == null ? 3 : (pair.sleepHours! / 9 * barMax).clamp(3, barMax),
                          color: pair.sleepHours == null ? p.wash : _sleepColor,
                          tooltip: pair.sleepHours == null
                              ? 'No sleep recorded'
                              : '${formatSleep(pair.sleepHours! * 60)} sleep',
                        ),
                        const SizedBox(width: 4),
                        _Bar(
                          height: pair.flow == null ? 3 : (pair.flow! / 100 * barMax).clamp(3, barMax),
                          color: pair.flow == null ? p.wash : p.leaf,
                          tooltip: pair.flow == null ? 'No work tracked' : 'Flow ${pair.flow}',
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(DateFormat('EEE').format(pair.day), style: SkyType.body(12).copyWith(color: p.inkMuted)),
                  ]),
                ),
            ]),
          ),
      ]),
    );
  }
}

const _sleepColor = Color(0xFF7D9FD9);

class _Bar extends StatelessWidget {
  final double height;
  final Color color;
  final String tooltip;
  const _Bar({required this.height, required this.color, required this.tooltip});

  @override
  Widget build(BuildContext context) => Tooltip(
        message: tooltip,
        child: Container(
          width: 20,
          height: height,
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
        ),
      );
}

class _MetricTile extends StatelessWidget {
  final String name;
  final String value;
  final List<double> series;
  final Color color;
  final String? note;

  const _MetricTile({
    required this.name,
    required this.value,
    required this.series,
    required this.color,
    required this.note,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Panel(
      radius: 24,
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 18),
      child: Semantics(
        container: true,
        label: name,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(name, style: SkyType.body(14).copyWith(color: p.inkOnSky)),
          const SizedBox(height: 6),
          Text(value, style: SkyType.figure(28)),
          const SizedBox(height: 10),
          SizedBox(
            height: 44,
            width: double.infinity,
            child: series.length < 2
                ? null
                : Semantics(
                    label: '$name over the last seven days',
                    child: CustomPaint(painter: _SparklinePainter(series, color)),
                  ),
          ),
          const SizedBox(height: 8),
          Text(note ?? 'No data this week', style: SkyType.body(13).copyWith(color: p.inkMuted)),
        ]),
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<double> values;
  final Color color;
  _SparklinePainter(this.values, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final lo = values.reduce((a, b) => a < b ? a : b);
    final hi = values.reduce((a, b) => a > b ? a : b);
    final span = hi - lo == 0 ? 1 : hi - lo;
    const pad = 3.0;
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = size.width * i / (values.length - 1);
      final y = pad + (size.height - pad * 2) * (1 - (values[i] - lo) / span);
      i == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_SparklinePainter old) => old.values != values || old.color != color;
}

/// Keeps the screen's content to a readable width on a wide window.
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
