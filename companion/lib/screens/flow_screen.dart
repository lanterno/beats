import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../services/repo_path.dart';
import '../theme/beats_refresh.dart';
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
  List<Map<String, dynamic>> _summaries = [];
  Map<String, int> _categoryTotals = {};
  int _totalSamples = 0;
  int? _selectedWindowIndex;
  // Top buckets from /flow-windows/summary — surfaced as a small "best
  // repo / best language today" line under the score gauge so the user
  // sees the same dimensions the web Insights chips expose without
  // having to open the browser. Null when the fetch failed or no
  // editor heartbeats covered the day.
  String? _topRepo;
  String? _topLanguage;

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
      // Single round-trip aggregate to surface the best-repo / best-
      // language hint alongside the gauge. Failure is non-fatal — the
      // gauge + timeline still render fine without it.
      final flowSummary = await widget.client.getFlowWindowsSummary(
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

      final topRepo = (flowSummary?['top_repo'] as Map?)?['key'] as String?;
      final topLanguage =
          (flowSummary?['top_language'] as Map?)?['key'] as String?;

      if (mounted) {
        setState(() {
          _windows = windows;
          _summaries = summaries;
          _currentScore = latest;
          _categoryTotals = cats;
          _totalSamples = total;
          _topRepo = topRepo;
          _topLanguage = topLanguage;
          _loading = false;
          _selectedWindowIndex = null;
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

  void _selectWindowAt(double dx, double width) {
    if (_windows.isEmpty || width <= 0) return;
    final ratio = (dx / width).clamp(0.0, 1.0);
    final idx = _windows.length == 1
        ? 0
        : (ratio * (_windows.length - 1)).round().clamp(0, _windows.length - 1);
    if (idx == _selectedWindowIndex) return;
    setState(() => _selectedWindowIndex = idx);
  }

  /// Picks the most recent summary whose hour ≤ the given window's start.
  /// Summaries are bucketed at the hour, so this lines up roughly with the
  /// window the user tapped on.
  Map<String, dynamic>? _summaryForWindow(Map<String, dynamic> window) {
    final start = DateTime.tryParse(window['window_start'] as String? ?? '');
    if (start == null || _summaries.isEmpty) return null;
    Map<String, dynamic>? best;
    DateTime? bestHour;
    for (final s in _summaries) {
      final h = DateTime.tryParse(s['hour'] as String? ?? '');
      if (h == null || h.isAfter(start)) continue;
      if (bestHour == null || h.isAfter(bestHour)) {
        bestHour = h;
        best = s;
      }
    }
    return best;
  }

  /// Returns the index of the window with the highest flow_score, with an
  /// earliest-peak tiebreak (matches the web's summarizeFlow). -1 only when
  /// _windows is empty, which the caller already guards against.
  int _peakWindowIndex() {
    if (_windows.isEmpty) return -1;
    var best = 0;
    var bestScore = -1.0;
    for (var i = 0; i < _windows.length; i++) {
      final score = (_windows[i]['flow_score'] as num?)?.toDouble() ?? 0.0;
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    return best;
  }

  /// Computes the day's avg flow score across `_windows`. Returns null on
  /// empty input so callers can render an empty state rather than 0/100.
  double? _todayAvgScore() {
    if (_windows.isEmpty) return null;
    var sum = 0.0;
    for (final w in _windows) {
      sum += (w['flow_score'] as num?)?.toDouble() ?? 0.0;
    }
    return sum / _windows.length;
  }

  Widget _buildStatsLine() {
    final idx = _peakWindowIndex();
    final avg = _todayAvgScore();
    if (idx < 0 || avg == null) return const SizedBox.shrink();
    final w = _windows[idx];
    final peakScore = (w['flow_score'] as num?)?.toDouble().clamp(0.0, 1.0) ?? 0.0;
    final start = DateTime.tryParse(w['window_start'] as String? ?? '')?.toLocal();
    if (start == null) return const SizedBox.shrink();
    final timeStr = '${start.hour.toString().padLeft(2, '0')}:${start.minute.toString().padLeft(2, '0')}';

    final labelStyle = BeatsType.label.copyWith(
      fontSize: 9, color: BeatsColors.textTertiary, letterSpacing: 2,
    );
    final numStyle = GoogleFonts.jetBrainsMono(
      fontSize: 13, color: BeatsColors.textPrimary, fontWeight: FontWeight.w400,
    );

    return Center(
      child: Wrap(
        alignment: WrapAlignment.center,
        spacing: 14,
        runSpacing: 6,
        children: [
          // AVG block
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('AVG', style: labelStyle),
              const SizedBox(width: 6),
              Text('${(avg * 100).round()}', style: numStyle),
            ],
          ),
          // PEAK block — tap to jump the inspector to the peak window.
          GestureDetector(
            onTap: () => setState(() => _selectedWindowIndex = idx),
            behavior: HitTestBehavior.opaque,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('PEAK', style: labelStyle),
                const SizedBox(width: 6),
                Text(
                  '${(peakScore * 100).round()}',
                  style: numStyle.copyWith(color: _scoreColor(peakScore)),
                ),
                const SizedBox(width: 4),
                Text('@', style: labelStyle),
                const SizedBox(width: 4),
                Text(
                  timeStr,
                  style: numStyle.copyWith(
                    color: BeatsColors.amber,
                    decoration: TextDecoration.underline,
                    decorationColor: BeatsColors.amber.withValues(alpha: 0.4),
                  ),
                ),
              ],
            ),
          ),
          // COUNT block
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('${_windows.length}',
                  style: numStyle.copyWith(color: BeatsColors.textSecondary)),
              const SizedBox(width: 6),
              Text(_windows.length == 1 ? 'WINDOW' : 'WINDOWS', style: labelStyle),
            ],
          ),
        ],
      ),
    );
  }

  /// "Best repo / best language today" line under the score gauge.
  /// Sourced from /flow-windows/summary's top buckets. Repo path is
  /// shortened to its last two segments (matches the daemon's
  /// shortRepoTrail and the web's shortRepoPath); language id is
  /// shown verbatim since there's no useful prettification (the web
  /// has a label map but it's a small enhancement that would warrant
  /// its own ship).
  Widget _buildTopDimensionsLine() {
    final labelStyle = BeatsType.label.copyWith(color: BeatsColors.textSecondary);
    final valueStyle = BeatsType.label.copyWith(
      color: BeatsColors.textPrimary,
      letterSpacing: 0.5,
    );
    final parts = <Widget>[];
    if (_topRepo != null) {
      parts.addAll([
        Text('BEST REPO', style: labelStyle),
        const SizedBox(width: 8),
        Text(shortRepoTail(_topRepo!), style: valueStyle),
      ]);
    }
    if (_topRepo != null && _topLanguage != null) {
      parts.add(const SizedBox(width: 18));
    }
    if (_topLanguage != null) {
      parts.addAll([
        Text('LANG', style: labelStyle),
        const SizedBox(width: 8),
        Text(_topLanguage!, style: valueStyle),
      ]);
    }
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: parts,
    );
  }

  Widget _buildSelectedWindowDetail() {
    final idx = _selectedWindowIndex;
    if (idx == null || idx >= _windows.length) return const SizedBox.shrink();
    final w = _windows[idx];
    final score = (w['flow_score'] as num?)?.toDouble().clamp(0.0, 1.0) ?? 0.0;
    final scoreInt = (score * 100).round();
    final start = DateTime.tryParse(w['window_start'] as String? ?? '')?.toLocal();
    final timeStr = start != null
        ? '${start.hour.toString().padLeft(2, '0')}:${start.minute.toString().padLeft(2, '0')}'
        : '—';

    final summary = _summaryForWindow(w);
    final cats = (summary?['categories'] as Map?)?.cast<String, dynamic>() ?? const {};
    final dominant = cats.entries
        .where((e) => (e.value as num?) != null)
        .toList()
      ..sort((a, b) => (b.value as num).compareTo(a.value as num));
    final topName = dominant.isNotEmpty ? dominant.first.key : null;
    final topColor = topName != null
        ? (_catColors[topName] ?? BeatsColors.textTertiary)
        : BeatsColors.textTertiary;

    // Editor context — present when the VS Code extension was sending
    // heartbeats during this window. We render the last two segments of
    // the path to keep the row width sane on long workspace paths.
    final repo = w['editor_repo'] as String?;
    final branch = w['editor_branch'] as String?;
    final repoShort = repo != null && repo.isNotEmpty ? _shortRepo(repo) : null;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: BeatsColors.border.withValues(alpha: 0.6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                timeStr,
                style: GoogleFonts.jetBrainsMono(
                  fontSize: 12, color: BeatsColors.textTertiary, letterSpacing: 1,
                ),
              ),
              const SizedBox(width: 14),
              Text('$scoreInt',
                style: GoogleFonts.jetBrainsMono(
                  fontSize: 16, color: _scoreColor(score), fontWeight: FontWeight.w400,
                )),
              Text(' / 100',
                style: BeatsType.bodySmall.copyWith(
                  fontSize: 11, color: BeatsColors.textTertiary)),
              const Spacer(),
              if (topName != null) ...[
                Container(width: 6, height: 6,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle, color: topColor)),
                const SizedBox(width: 6),
                Text(topName.toUpperCase(),
                  style: BeatsType.label.copyWith(
                    fontSize: 9, color: BeatsColors.textSecondary, letterSpacing: 1.5)),
              ],
            ],
          ),
          if (repoShort != null) ...[
            const SizedBox(height: 6),
            Row(
              children: [
                Icon(Icons.folder_outlined,
                    size: 11, color: BeatsColors.textTertiary.withValues(alpha: 0.7)),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    repoShort,
                    overflow: TextOverflow.ellipsis,
                    style: BeatsType.bodySmall.copyWith(
                      fontSize: 11,
                      color: BeatsColors.textSecondary,
                    ),
                  ),
                ),
                if (branch != null && branch.isNotEmpty) ...[
                  Text(' · ',
                    style: BeatsType.bodySmall.copyWith(
                      fontSize: 11, color: BeatsColors.textTertiary)),
                  Text(branch,
                    style: BeatsType.bodySmall.copyWith(
                      fontSize: 11, color: BeatsColors.textTertiary)),
                ],
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// Returns the last two segments of a path so a 60-char workspace
  /// stays readable in the inspector row.
  String _shortRepo(String path) {
    final parts = path.split(RegExp(r'[\\/]')).where((s) => s.isNotEmpty).toList();
    if (parts.length <= 2) return path;
    return parts.sublist(parts.length - 2).join('/');
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
          child: BeatsRefresh(
            onRefresh: _refresh,
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
                const SizedBox(height: 16),

                // ── Today's stats: avg · peak (with click-to-jump) · count ──
                // Density of info matches the web's FlowToday header but in
                // the brutalist label style. Hidden when there's only one
                // window — it would duplicate the ring above.
                if (_windows.length > 1) _buildStatsLine(),

                // ── Top dimensions today (best repo / best language) ──
                // Sourced from /api/signals/flow-windows/summary so it's a
                // single round-trip aggregate, not derived client-side.
                // Hidden when both axes are empty — windows without editor
                // heartbeats wouldn't have anything to surface here.
                if (_topRepo != null || _topLanguage != null) ...[
                  const SizedBox(height: 12),
                  _buildTopDimensionsLine(),
                ],

                const SizedBox(height: 24),

                // ── Timeline ──
                if (_windows.isNotEmpty) ...[
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('TODAY', style: BeatsType.label),
                        const SizedBox(height: 14),
                        LayoutBuilder(builder: (_, constraints) {
                          return GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTapDown: (d) => _selectWindowAt(d.localPosition.dx, constraints.maxWidth),
                            onPanUpdate: (d) => _selectWindowAt(d.localPosition.dx, constraints.maxWidth),
                            onPanEnd: (_) {},
                            child: SizedBox(
                              height: 72,
                              child: CustomPaint(
                                size: const Size(double.infinity, 72),
                                painter: _AreaPainter(
                                  _windows,
                                  selectedIndex: _selectedWindowIndex,
                                ),
                              ),
                            ),
                          );
                        }),
                        if (_selectedWindowIndex != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: _buildSelectedWindowDetail(),
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

    // Inner radial gradient — gives the ring's interior a quiet glow that
    // tints with the score color so the digits read as part of a luminous
    // disc rather than floating on a flat ground.
    final innerRect = Rect.fromCircle(center: center, radius: radius);
    canvas.drawCircle(
      center,
      radius - 1.5,
      Paint()
        ..shader = RadialGradient(
          colors: [
            color.withValues(alpha: 0.06),
            BeatsColors.background.withValues(alpha: 0),
          ],
          stops: const [0.0, 1.0],
        ).createShader(innerRect),
    );

    // Background ring
    canvas.drawCircle(center, radius, Paint()
      ..color = BeatsColors.border.withValues(alpha: 0.4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3);

    // Score arc — a sweep gradient from amber-warm into a softer warm-white,
    // rotated so the gradient starts at the top (matching the arc's start).
    if (score > 0) {
      final arcRect = Rect.fromCircle(center: center, radius: radius);
      final endColor = Color.lerp(color, const Color(0xFFFFE4B5), 0.55) ?? color;
      final shader = SweepGradient(
        startAngle: 0,
        endAngle: 2 * pi,
        colors: [color, endColor, color],
        transform: GradientRotation(-pi / 2),
      ).createShader(arcRect);
      canvas.drawArc(
        arcRect,
        -pi / 2,
        2 * pi * score.clamp(0.0, 1.0),
        false,
        Paint()
          ..shader = shader
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
  final int? selectedIndex;
  _AreaPainter(this.windows, {this.selectedIndex});

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
    for (final p in points) {
      area.lineTo(p.dx, p.dy);
    }
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
      if (i == 0) {
        line.moveTo(points[i].dx, points[i].dy);
      } else {
        line.lineTo(points[i].dx, points[i].dy);
      }
    }
    canvas.drawPath(line, Paint()
      ..color = BeatsColors.amber
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round);

    // Selected-point marker: vertical guide + filled dot.
    final sel = selectedIndex;
    if (sel != null && sel >= 0 && sel < points.length) {
      final p = points[sel];
      canvas.drawLine(
        Offset(p.dx, 0),
        Offset(p.dx, size.height),
        Paint()
          ..color = BeatsColors.amber.withValues(alpha: 0.35)
          ..strokeWidth = 1,
      );
      canvas.drawCircle(p, 4.5,
          Paint()..color = BeatsColors.background);
      canvas.drawCircle(p, 3.5,
          Paint()..color = BeatsColors.amber);
    }
  }

  @override
  bool shouldRepaint(covariant _AreaPainter old) => true;
}
