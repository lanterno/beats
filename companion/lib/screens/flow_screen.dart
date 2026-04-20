import 'dart:math';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';

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
    final start = startOfDay.toIso8601String();
    final end = now.toIso8601String();

    try {
      final windows = await widget.client.getFlowWindows(start, end);
      final summaries = await widget.client.getSignalSummaries(start, end);

      // Aggregate categories
      final cats = <String, int>{};
      var total = 0;
      for (final s in summaries) {
        final c = s['categories'] as Map<String, dynamic>? ?? {};
        for (final e in c.entries) {
          cats[e.key] = (cats[e.key] ?? 0) + (e.value as int);
        }
        total += (s['total_samples'] as int?) ?? 0;
      }

      // Latest score
      final latest = windows.isNotEmpty ? (windows.last['flow_score'] as num).toDouble() : 0.0;

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

  Color _scoreColor(double score) {
    if (score >= 0.7) return Colors.green;
    if (score >= 0.3) return Colors.amber;
    return Colors.red.shade400;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: BeatsColors.amber));
    }

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          // Flow score gauge
          Center(
            child: SizedBox(
              width: 180,
              height: 180,
              child: CustomPaint(
                painter: _ScoreGaugePainter(_currentScore, _scoreColor(_currentScore)),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${(_currentScore * 100).round()}',
                        style: theme.textTheme.displayMedium?.copyWith(
                          fontWeight: FontWeight.w200,
                        ),
                      ),
                      Text(
                        'Flow Score',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 32),

          // Today's flow timeline
          if (_windows.isNotEmpty) ...[
            Text('Today\'s flow', style: theme.textTheme.titleSmall),
            const SizedBox(height: 12),
            SizedBox(
              height: 60,
              child: Row(
                children: _windows.map((w) {
                  final score = (w['flow_score'] as num).toDouble();
                  return Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 1),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Flexible(
                            child: FractionallySizedBox(
                              heightFactor: score.clamp(0.05, 1.0),
                              child: Container(
                                decoration: BoxDecoration(
                                  color: _scoreColor(score),
                                  borderRadius: BorderRadius.circular(2),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 24),
          ],

          // Category breakdown
          if (_categoryTotals.isNotEmpty) ...[
            Text('Activity breakdown', style: theme.textTheme.titleSmall),
            const SizedBox(height: 12),
            ..._sortedCategories().map((e) {
              final fraction = _totalSamples > 0 ? e.value / _totalSamples : 0.0;
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    SizedBox(
                      width: 90,
                      child: Text(
                        e.key,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                        ),
                      ),
                    ),
                    Expanded(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: fraction,
                          minHeight: 8,
                          backgroundColor: theme.colorScheme.surfaceContainerHighest,
                          color: theme.colorScheme.primary,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${(fraction * 100).round()}%',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              );
            }),
          ],

          if (_windows.isEmpty && _categoryTotals.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.only(top: 48),
                child: Text(
                  'No flow data today yet.\nStart the daemon to begin collecting.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
        ],
      ),
    );
  }

  List<MapEntry<String, int>> _sortedCategories() {
    final entries = _categoryTotals.entries.toList();
    entries.sort((a, b) => b.value.compareTo(a.value));
    return entries;
  }
}

class _ScoreGaugePainter extends CustomPainter {
  final double score;
  final Color color;
  _ScoreGaugePainter(this.score, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 8;

    // Background arc
    final bgPaint = Paint()
      ..color = color.withValues(alpha: 0.15)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi * 0.75,
      pi * 1.5,
      false,
      bgPaint,
    );

    // Score arc
    final scorePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi * 0.75,
      pi * 1.5 * score.clamp(0.0, 1.0),
      false,
      scorePaint,
    );
  }

  @override
  bool shouldRepaint(covariant _ScoreGaugePainter old) =>
      old.score != score || old.color != color;
}
