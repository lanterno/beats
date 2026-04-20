import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

// Category colors matching web UI
const _catColors = {
  'coding': Color(0xFF5B9CF6),
  'communication': Color(0xFFA78BFA),
  'browser': Color(0xFF22D3EE),
  'design': Color(0xFFF472B6),
  'writing': Color(0xFFFBBF24),
  'social': Color(0xFFFB923C),
  'other': Color(0xFF6B6155),
};

class FlowScreen extends StatefulWidget {
  final ApiClient client;
  const FlowScreen({super.key, required this.client});

  @override
  State<FlowScreen> createState() => _FlowScreenState();
}

class _FlowScreenState extends State<FlowScreen> {
  bool _loading = true;
  double _currentScore = 0.0;
  List<Map<String, dynamic>> _windows = [];
  Map<String, int> _categoryTotals = {};
  int _totalSamples = 0;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    final now = DateTime.now().toUtc();
    final startOfDay = DateTime.utc(now.year, now.month, now.day);
    try {
      final windows = await widget.client.getFlowWindows(
          startOfDay.toIso8601String(), now.toIso8601String());
      final summaries = await widget.client.getSignalSummaries(
          startOfDay.toIso8601String(), now.toIso8601String());

      final cats = <String, int>{};
      var total = 0;
      for (final s in summaries) {
        final c = s['categories'] as Map<String, dynamic>? ?? {};
        for (final e in c.entries) {
          cats[e.key] = (cats[e.key] ?? 0) + (e.value as int);
        }
        total += (s['total_samples'] as int?) ?? 0;
      }
      final latest = windows.isNotEmpty
          ? (windows.last['flow_score'] as num).toDouble()
          : 0.0;

      if (mounted) {
        setState(() {
          _windows = windows;
          _currentScore = latest;
          _categoryTotals = cats;
          _totalSamples = total;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Color _scoreColor(double s) {
    if (s >= 0.7) return BeatsColors.green;
    if (s >= 0.3) return BeatsColors.amber;
    return BeatsColors.red;
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: BeatsColors.amber));
    }

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          color: BeatsColors.amber,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 80),
            children: [
              // Score gauge
              StaggeredEntrance(
                child: Center(
                  child: SizedBox(
                    width: 200, height: 200,
                    child: CustomPaint(
                      painter: _GradientGaugePainter(_currentScore, _scoreColor(_currentScore)),
                      child: Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              '${(_currentScore * 100).round()}',
                              style: GoogleFonts.dmSerifDisplay(
                                fontSize: 48,
                                color: BeatsColors.textPrimary,
                                fontWeight: FontWeight.w400,
                              ),
                            ),
                            Text('/ 100',
                                style: BeatsType.bodySmall.copyWith(
                                    color: BeatsColors.textTertiary, fontSize: 13)),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              StaggeredEntrance(
                delay: const Duration(milliseconds: 60),
                child: Center(
                  child: Text('FLOW SCORE', style: BeatsType.label),
                ),
              ),
              const SizedBox(height: 32),

              // Timeline
              if (_windows.isNotEmpty) ...[
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 120),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Today's flow", style: BeatsType.titleSmall),
                      const SizedBox(height: 12),
                      SizedBox(
                        height: 64,
                        child: CustomPaint(
                          size: Size(double.infinity, 64),
                          painter: _AreaChartPainter(_windows),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 28),
              ],

              // Categories
              if (_categoryTotals.isNotEmpty) ...[
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 180),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Activity breakdown', style: BeatsType.titleSmall),
                      const SizedBox(height: 14),
                      ..._sortedCategories().asMap().entries.map((entry) {
                        final i = entry.key;
                        final e = entry.value;
                        final fraction = _totalSamples > 0 ? e.value / _totalSamples : 0.0;
                        final color = _catColors[e.key] ?? BeatsColors.textTertiary;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Row(
                            children: [
                              Container(
                                width: 4, height: 16,
                                decoration: BoxDecoration(
                                  color: color,
                                  borderRadius: BorderRadius.circular(2),
                                ),
                              ),
                              const SizedBox(width: 10),
                              SizedBox(
                                width: 85,
                                child: Text(e.key,
                                    style: BeatsType.bodySmall.copyWith(
                                        color: BeatsColors.textSecondary)),
                              ),
                              Expanded(
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(4),
                                  child: TweenAnimationBuilder<double>(
                                    tween: Tween(begin: 0, end: fraction),
                                    duration: Duration(milliseconds: 400 + i * 100),
                                    curve: Curves.easeOutCubic,
                                    builder: (_, val, _) => LinearProgressIndicator(
                                      value: val,
                                      minHeight: 6,
                                      backgroundColor: BeatsColors.border,
                                      color: color,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 10),
                              SizedBox(
                                width: 36,
                                child: Text(
                                  '${(fraction * 100).round()}%',
                                  style: BeatsType.monoSmall.copyWith(
                                      fontSize: 12, color: BeatsColors.textSecondary),
                                  textAlign: TextAlign.right,
                                ),
                              ),
                            ],
                          ),
                        );
                      }),
                    ],
                  ),
                ),
              ],

              if (_windows.isEmpty && _categoryTotals.isEmpty)
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 120),
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 40),
                      child: Column(
                        children: [
                          Icon(Icons.insights, size: 40,
                              color: BeatsColors.textTertiary.withValues(alpha: 0.3)),
                          const SizedBox(height: 12),
                          Text('No flow data today yet',
                              style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary)),
                          const SizedBox(height: 4),
                          Text('Start the daemon to begin collecting',
                              style: BeatsType.bodySmall.copyWith(
                                  color: BeatsColors.textTertiary.withValues(alpha: 0.6))),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  List<MapEntry<String, int>> _sortedCategories() {
    final entries = _categoryTotals.entries.toList();
    entries.sort((a, b) => b.value.compareTo(a.value));
    return entries;
  }
}

// Full-circle gradient gauge
class _GradientGaugePainter extends CustomPainter {
  final double score;
  final Color color;
  _GradientGaugePainter(this.score, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 10;
    final rect = Rect.fromCircle(center: center, radius: radius);

    // Background ring
    canvas.drawCircle(
      center, radius,
      Paint()
        ..color = color.withValues(alpha: 0.06)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 8,
    );

    // Score arc with gradient
    if (score > 0) {
      final sweep = 2 * pi * score.clamp(0.0, 1.0);
      final gradient = SweepGradient(
        startAngle: -pi / 2,
        endAngle: -pi / 2 + sweep,
        colors: [color.withValues(alpha: 0.4), color],
      );
      canvas.drawArc(
        rect, -pi / 2, sweep, false,
        Paint()
          ..shader = gradient.createShader(rect)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 8
          ..strokeCap = StrokeCap.round,
      );
    }

    // Glow at score > 0.7
    if (score >= 0.7) {
      canvas.drawCircle(
        center, radius,
        Paint()
          ..color = color.withValues(alpha: 0.08)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 16),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _GradientGaugePainter old) =>
      old.score != score || old.color != color;
}

// Smooth area chart for flow timeline
class _AreaChartPainter extends CustomPainter {
  final List<Map<String, dynamic>> windows;
  _AreaChartPainter(this.windows);

  @override
  void paint(Canvas canvas, Size size) {
    if (windows.isEmpty) return;

    final points = <Offset>[];
    for (var i = 0; i < windows.length; i++) {
      final score = (windows[i]['flow_score'] as num).toDouble().clamp(0.0, 1.0);
      final x = windows.length == 1
          ? size.width / 2
          : i / (windows.length - 1) * size.width;
      final y = size.height - score * size.height;
      points.add(Offset(x, y));
    }

    // Area fill
    final areaPath = Path()..moveTo(0, size.height);
    for (final p in points) {
      areaPath.lineTo(p.dx, p.dy);
    }
    areaPath.lineTo(size.width, size.height);
    areaPath.close();

    final gradient = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: [
        BeatsColors.amber.withValues(alpha: 0.25),
        BeatsColors.amber.withValues(alpha: 0.02),
      ],
    );
    canvas.drawPath(
      areaPath,
      Paint()..shader = gradient.createShader(Rect.fromLTWH(0, 0, size.width, size.height)),
    );

    // Line
    final linePath = Path();
    for (var i = 0; i < points.length; i++) {
      if (i == 0) {
        linePath.moveTo(points[i].dx, points[i].dy);
      } else {
        linePath.lineTo(points[i].dx, points[i].dy);
      }
    }
    canvas.drawPath(
      linePath,
      Paint()
        ..color = BeatsColors.amber
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(covariant _AreaChartPainter old) => true;
}
