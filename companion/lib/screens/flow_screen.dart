import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

const _catColors = {
  'coding': Color(0xFF5B9CF6),
  'communication': Color(0xFFA78BFA),
  'browser': Color(0xFF22D3EE),
  'design': Color(0xFFF472B6),
  'writing': Color(0xFFFBBF24),
  'social': Color(0xFFFB923C),
  'other': Color(0xFF5C5247),
};

class FlowScreen extends StatefulWidget {
  final ApiClient client;
  const FlowScreen({super.key, required this.client});

  @override
  State<FlowScreen> createState() => _FlowScreenState();
}

class _FlowScreenState extends State<FlowScreen> with SingleTickerProviderStateMixin {
  bool _loading = true;
  double _currentScore = 0.0;
  List<Map<String, dynamic>> _windows = [];
  Map<String, int> _categoryTotals = {};
  int _totalSamples = 0;

  late AnimationController _glowController;

  @override
  void initState() {
    super.initState();
    _glowController = AnimationController(
      vsync: this, duration: const Duration(seconds: 3),
    )..repeat(reverse: true);
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
          ? (windows.last['flow_score'] as num).toDouble() : 0.0;

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
  void dispose() {
    _glowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    final color = _scoreColor(_currentScore);
    final scoreInt = (_currentScore * 100).round();

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: Container(
        decoration: _currentScore > 0
            ? BoxDecoration(
                gradient: RadialGradient(
                  center: const Alignment(0, -0.6),
                  radius: 1.4,
                  colors: [color.withValues(alpha: 0.05), BeatsColors.background],
                ),
              )
            : null,
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: _refresh,
            color: BeatsColors.amber,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
              children: [
                // ── Label ──
                StaggeredEntrance(
                  child: Center(
                    child: Text('FLOW', style: BeatsType.label.copyWith(
                      letterSpacing: 6, fontSize: 11, color: BeatsColors.textTertiary)),
                  ),
                ),
                const SizedBox(height: 32),

                // ── Giant score ──
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 60),
                  child: Center(
                    child: AnimatedBuilder(
                      animation: _glowController,
                      builder: (_, _) => Container(
                        decoration: _currentScore >= 0.7
                            ? BoxDecoration(
                                shape: BoxShape.circle,
                                boxShadow: [BoxShadow(
                                  color: color.withValues(
                                      alpha: 0.08 + _glowController.value * 0.08),
                                  blurRadius: 80, spreadRadius: 20,
                                )],
                              )
                            : null,
                        child: SizedBox(
                          width: 200, height: 200,
                          child: CustomPaint(
                            painter: _RingPainter(_currentScore, color),
                            child: Center(
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text('$scoreInt',
                                    style: GoogleFonts.jetBrainsMono(
                                      fontSize: 56, fontWeight: FontWeight.w200,
                                      color: BeatsColors.textPrimary, height: 1,
                                    )),
                                  Text('/ 100',
                                    style: BeatsType.bodySmall.copyWith(
                                      color: BeatsColors.textTertiary, fontSize: 12)),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 40),

                // ── Timeline ──
                if (_windows.isNotEmpty) ...[
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('TODAY', style: BeatsType.label),
                        const SizedBox(height: 14),
                        SizedBox(
                          height: 72,
                          child: CustomPaint(
                            size: const Size(double.infinity, 72),
                            painter: _AreaPainter(_windows),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 36),
                ],

                // ── Categories ──
                if (_categoryTotals.isNotEmpty) ...[
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 180),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('ACTIVITY', style: BeatsType.label),
                        const SizedBox(height: 16),
                        ..._sortedCats().asMap().entries.map((entry) {
                          final i = entry.key;
                          final e = entry.value;
                          final frac = _totalSamples > 0 ? e.value / _totalSamples : 0.0;
                          final c = _catColors[e.key] ?? BeatsColors.textTertiary;
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 14),
                            child: Row(
                              children: [
                                Container(width: 3, height: 20,
                                  decoration: BoxDecoration(
                                    color: c, borderRadius: BorderRadius.circular(2))),
                                const SizedBox(width: 12),
                                SizedBox(width: 90,
                                  child: Text(e.key,
                                    style: BeatsType.bodySmall.copyWith(
                                      color: BeatsColors.textSecondary, fontSize: 13))),
                                Expanded(
                                  child: TweenAnimationBuilder<double>(
                                    tween: Tween(begin: 0, end: frac),
                                    duration: Duration(milliseconds: 500 + i * 120),
                                    curve: Curves.easeOutCubic,
                                    builder: (_, val, _) => Container(
                                      height: 4,
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(2),
                                        color: BeatsColors.border,
                                      ),
                                      child: FractionallySizedBox(
                                        alignment: Alignment.centerLeft,
                                        widthFactor: val.clamp(0, 1),
                                        child: Container(
                                          decoration: BoxDecoration(
                                            borderRadius: BorderRadius.circular(2),
                                            color: c,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                SizedBox(width: 38, child: Text(
                                  '${(frac * 100).round()}%',
                                  style: GoogleFonts.jetBrainsMono(
                                    fontSize: 11, color: BeatsColors.textTertiary),
                                  textAlign: TextAlign.right,
                                )),
                              ],
                            ),
                          );
                        }),
                      ],
                    ),
                  ),
                ],

                // ── Empty state ──
                if (_windows.isEmpty && _categoryTotals.isEmpty)
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: Padding(
                      padding: const EdgeInsets.only(top: 32),
                      child: Center(
                        child: Column(
                          children: [
                            Icon(Icons.air, size: 36,
                                color: BeatsColors.textTertiary.withValues(alpha: 0.2)),
                            const SizedBox(height: 16),
                            Text('No flow data today',
                              style: BeatsType.bodyMedium.copyWith(
                                color: BeatsColors.textTertiary)),
                            const SizedBox(height: 4),
                            Text('Start the daemon to begin collecting',
                              style: BeatsType.bodySmall.copyWith(
                                color: BeatsColors.textTertiary.withValues(alpha: 0.5))),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<MapEntry<String, int>> _sortedCats() {
    final entries = _categoryTotals.entries.toList();
    entries.sort((a, b) => b.value.compareTo(a.value));
    return entries;
  }
}

class _RingPainter extends CustomPainter {
  final double score;
  final Color color;
  _RingPainter(this.score, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 12;

    // Background ring
    canvas.drawCircle(center, radius, Paint()
      ..color = BeatsColors.border.withValues(alpha: 0.4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3);

    // Score arc
    if (score > 0) {
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        -pi / 2,
        2 * pi * score.clamp(0.0, 1.0),
        false,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3
          ..strokeCap = StrokeCap.round,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _RingPainter old) =>
      old.score != score || old.color != color;
}

class _AreaPainter extends CustomPainter {
  final List<Map<String, dynamic>> windows;
  _AreaPainter(this.windows);

  @override
  void paint(Canvas canvas, Size size) {
    if (windows.isEmpty) return;

    final points = <Offset>[];
    for (var i = 0; i < windows.length; i++) {
      final s = (windows[i]['flow_score'] as num).toDouble().clamp(0.0, 1.0);
      final x = windows.length == 1 ? size.width / 2 : i / (windows.length - 1) * size.width;
      points.add(Offset(x, size.height - s * size.height * 0.85));
    }

    // Area
    final area = Path()..moveTo(0, size.height);
    for (final p in points) area.lineTo(p.dx, p.dy);
    area.lineTo(size.width, size.height);
    area.close();
    canvas.drawPath(area, Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [BeatsColors.amber.withValues(alpha: 0.2), Colors.transparent],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height)));

    // Line
    final line = Path();
    for (var i = 0; i < points.length; i++) {
      if (i == 0) line.moveTo(points[i].dx, points[i].dy);
      else line.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(line, Paint()
      ..color = BeatsColors.amber
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round);
  }

  @override
  bool shouldRepaint(covariant _AreaPainter old) => true;
}
