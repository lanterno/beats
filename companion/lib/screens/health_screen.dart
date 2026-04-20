import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

class HealthScreen extends StatefulWidget {
  final ApiClient client;
  const HealthScreen({super.key, required this.client});

  @override
  State<HealthScreen> createState() => _HealthScreenState();
}

class _HealthScreenState extends State<HealthScreen> {
  bool _loading = true;
  List<Map<String, dynamic>> _days = [];

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    final now = DateTime.now();
    final start = now.subtract(const Duration(days: 7));
    try {
      final data = await widget.client.getBiometrics(
        '${start.year}-${start.month.toString().padLeft(2, '0')}-${start.day.toString().padLeft(2, '0')}',
        '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}',
      );
      if (mounted) setState(() { _days = data; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  // Get latest value for a field
  dynamic _latest(String field) {
    for (var i = _days.length - 1; i >= 0; i--) {
      if (_days[i][field] != null) return _days[i][field];
    }
    return null;
  }

  // Get list of values for sparkline
  List<double> _sparkline(String field) {
    return _days
        .where((d) => d[field] != null)
        .map<double>((d) => (d[field] as num).toDouble())
        .toList();
  }

  // Compute 7-day average
  double? _avg(String field) {
    final vals = _sparkline(field);
    if (vals.isEmpty) return null;
    return vals.reduce((a, b) => a + b) / vals.length;
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    final sleepMin = _latest('sleep_minutes') as int?;
    final sleepHours = sleepMin != null ? sleepMin / 60.0 : null;
    final sleepEff = _latest('sleep_efficiency') as num?;
    final hrv = _latest('hrv_ms') as num?;
    final restHr = _latest('resting_hr_bpm') as int?;
    final steps = _latest('steps') as int?;
    final readiness = _latest('readiness_score') as int?;

    final hasData = sleepMin != null || hrv != null || steps != null;

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          color: BeatsColors.amber,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
            children: [
              StaggeredEntrance(
                child: Text('Health',
                  style: GoogleFonts.dmSerifDisplay(
                    fontSize: 32, color: BeatsColors.textPrimary)),
              ),
              const SizedBox(height: 28),

              if (!hasData) ...[
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 80),
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 40),
                      child: Column(
                        children: [
                          Icon(Icons.monitor_heart_outlined, size: 36,
                            color: BeatsColors.textTertiary.withValues(alpha: 0.2)),
                          const SizedBox(height: 16),
                          Text('No biometric data yet',
                            style: BeatsType.bodyMedium.copyWith(
                              color: BeatsColors.textTertiary)),
                          const SizedBox(height: 4),
                          Text('Connect Fitbit or Oura in Settings',
                            style: BeatsType.bodySmall.copyWith(
                              color: BeatsColors.textTertiary.withValues(alpha: 0.5))),
                        ],
                      ),
                    ),
                  ),
                ),
              ],

              if (hasData) ...[
                // ── Sleep ──
                if (sleepMin != null)
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 60),
                    child: _MetricCard(
                      icon: Icons.bedtime_outlined,
                      label: 'SLEEP',
                      value: '${sleepHours!.toStringAsFixed(1)}h',
                      subtitle: sleepEff != null
                          ? '${(sleepEff.toDouble() * 100).round()}% efficiency'
                          : null,
                      sparkline: _sparkline('sleep_minutes').map((v) => v / 60).toList(),
                      color: const Color(0xFF818CF8), // indigo
                      avg: _avg('sleep_minutes') != null
                          ? '${(_avg('sleep_minutes')! / 60).toStringAsFixed(1)}h avg'
                          : null,
                    ),
                  ),

                // ── HRV ──
                if (hrv != null) ...[
                  const SizedBox(height: 16),
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: _MetricCard(
                      icon: Icons.favorite_outline,
                      label: 'HRV',
                      value: '${hrv.round()}ms',
                      sparkline: _sparkline('hrv_ms'),
                      color: BeatsColors.green,
                      avg: _avg('hrv_ms') != null
                          ? '${_avg('hrv_ms')!.round()}ms avg'
                          : null,
                    ),
                  ),
                ],

                // ── Resting HR ──
                if (restHr != null) ...[
                  const SizedBox(height: 16),
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 180),
                    child: _MetricCard(
                      icon: Icons.monitor_heart_outlined,
                      label: 'RESTING HR',
                      value: '${restHr}bpm',
                      sparkline: _sparkline('resting_hr_bpm'),
                      color: BeatsColors.red,
                      avg: _avg('resting_hr_bpm') != null
                          ? '${_avg('resting_hr_bpm')!.round()}bpm avg'
                          : null,
                    ),
                  ),
                ],

                // ── Steps ──
                if (steps != null) ...[
                  const SizedBox(height: 16),
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 240),
                    child: _MetricCard(
                      icon: Icons.directions_walk,
                      label: 'STEPS',
                      value: _formatSteps(steps),
                      sparkline: _sparkline('steps'),
                      color: BeatsColors.amber,
                      avg: _avg('steps') != null
                          ? '${_formatSteps(_avg('steps')!.round())} avg'
                          : null,
                    ),
                  ),
                ],

                // ── Readiness ──
                if (readiness != null) ...[
                  const SizedBox(height: 16),
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 300),
                    child: _ReadinessCard(score: readiness),
                  ),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatSteps(int s) => s >= 1000 ? '${(s / 1000).toStringAsFixed(1)}k' : '$s';
}

// ─── Metric card with sparkline ─────────────────────────────────────

class _MetricCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String? subtitle;
  final List<double> sparkline;
  final Color color;
  final String? avg;

  const _MetricCard({
    required this.icon,
    required this.label,
    required this.value,
    this.subtitle,
    required this.sparkline,
    required this.color,
    this.avg,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: BeatsColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: color.withValues(alpha: 0.6)),
              const SizedBox(width: 8),
              Text(label, style: BeatsType.label.copyWith(color: color.withValues(alpha: 0.7))),
              const Spacer(),
              if (avg != null)
                Text(avg!, style: BeatsType.bodySmall.copyWith(
                  color: BeatsColors.textTertiary, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(value, style: GoogleFonts.jetBrainsMono(
                fontSize: 32, fontWeight: FontWeight.w300,
                color: BeatsColors.textPrimary, height: 1)),
              if (subtitle != null) ...[
                const SizedBox(width: 10),
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(subtitle!,
                    style: BeatsType.bodySmall.copyWith(
                      color: BeatsColors.textTertiary, fontSize: 12)),
                ),
              ],
            ],
          ),
          if (sparkline.length >= 2) ...[
            const SizedBox(height: 16),
            SizedBox(
              height: 32,
              child: CustomPaint(
                size: const Size(double.infinity, 32),
                painter: _SparklinePainter(sparkline, color),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ─── Readiness card ─────────────────────────────────────────────────

class _ReadinessCard extends StatelessWidget {
  final int score;
  const _ReadinessCard({required this.score});

  @override
  Widget build(BuildContext context) {
    final color = score >= 80
        ? BeatsColors.green
        : score >= 60
            ? BeatsColors.amber
            : BeatsColors.red;
    final label = score >= 80 ? 'Ready to push' : score >= 60 ? 'Moderate' : 'Take it easy';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: BeatsColors.border),
      ),
      child: Row(
        children: [
          // Score ring
          SizedBox(
            width: 56, height: 56,
            child: CustomPaint(
              painter: _ReadinessRingPainter(score / 100.0, color),
              child: Center(
                child: Text('$score',
                  style: GoogleFonts.jetBrainsMono(
                    fontSize: 18, fontWeight: FontWeight.w400,
                    color: BeatsColors.textPrimary)),
              ),
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('READINESS', style: BeatsType.label.copyWith(
                  color: color.withValues(alpha: 0.7))),
                const SizedBox(height: 4),
                Text(label, style: BeatsType.bodyMedium.copyWith(
                  color: BeatsColors.textSecondary)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReadinessRingPainter extends CustomPainter {
  final double progress;
  final Color color;
  _ReadinessRingPainter(this.progress, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 4;

    canvas.drawCircle(center, radius, Paint()
      ..color = BeatsColors.border
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3);

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi / 2,
      2 * pi * progress.clamp(0.0, 1.0),
      false,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(covariant _ReadinessRingPainter old) =>
      old.progress != progress || old.color != color;
}

// ─── Sparkline painter ──────────────────────────────────────────────

class _SparklinePainter extends CustomPainter {
  final List<double> data;
  final Color color;
  _SparklinePainter(this.data, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    if (data.length < 2) return;

    final minVal = data.reduce(min);
    final maxVal = data.reduce(max);
    final range = maxVal - minVal;
    if (range == 0) return;

    final points = <Offset>[];
    for (var i = 0; i < data.length; i++) {
      final x = i / (data.length - 1) * size.width;
      final y = size.height - ((data[i] - minVal) / range) * size.height * 0.8 - size.height * 0.1;
      points.add(Offset(x, y));
    }

    // Area
    final area = Path()..moveTo(0, size.height);
    for (final p in points) area.lineTo(p.dx, p.dy);
    area.lineTo(size.width, size.height);
    area.close();
    canvas.drawPath(area, Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [color.withValues(alpha: 0.15), Colors.transparent],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height)));

    // Line
    final line = Path();
    for (var i = 0; i < points.length; i++) {
      if (i == 0) line.moveTo(points[i].dx, points[i].dy);
      else line.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(line, Paint()
      ..color = color.withValues(alpha: 0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round);

    // Last point dot
    canvas.drawCircle(points.last, 3, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter old) => true;
}
