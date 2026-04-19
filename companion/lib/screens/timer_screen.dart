import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/api_client.dart';

class TimerScreen extends StatefulWidget {
  final ApiClient client;
  const TimerScreen({super.key, required this.client});

  @override
  State<TimerScreen> createState() => _TimerScreenState();
}

class _TimerScreenState extends State<TimerScreen> with TickerProviderStateMixin {
  bool _loading = true;
  bool _running = false;
  String? _projectName;
  List<int> _projectColor = [212, 149, 42];
  DateTime? _startTime;
  Duration _elapsed = Duration.zero;
  Timer? _ticker;
  String? _error;
  List<Map<String, dynamic>> _projects = [];

  // Pulse animation for running state
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 0.08, end: 0.2).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final status = await widget.client.getTimerStatus();
      final projects = await widget.client.getProjects();
      if (mounted) {
        setState(() {
          _projects = projects;
          _running = status['running'] == true;
          _error = null;
          if (_running && status['beat'] != null) {
            final beat = status['beat'];
            _projectName = status['project_name'] ?? beat['project_id'];
            _startTime = DateTime.parse(beat['start']);
            _elapsed = DateTime.now().toUtc().difference(_startTime!);
            _startTicker();
          } else {
            _stopTicker();
            _projectName = null;
            _startTime = null;
            _elapsed = Duration.zero;
          }
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = '$e'; _loading = false; });
    }
  }

  void _startTicker() {
    _stopTicker();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_startTime != null && mounted) {
        setState(() => _elapsed = DateTime.now().toUtc().difference(_startTime!));
      }
    });
  }

  void _stopTicker() { _ticker?.cancel(); _ticker = null; }

  Future<void> _start(String projectId, String name, List<int> color) async {
    setState(() {
      _running = true;
      _projectName = name;
      _projectColor = color;
      _startTime = DateTime.now().toUtc();
      _elapsed = Duration.zero;
      _error = null;
    });
    _startTicker();
    try { await widget.client.startTimer(projectId); }
    catch (e) { setState(() => _error = '$e'); await _refresh(); }
  }

  Future<void> _stop() async {
    _stopTicker();
    final was = _running;
    setState(() { _running = false; _error = null; });
    try {
      await widget.client.stopTimer();
      setState(() { _projectName = null; _startTime = null; _elapsed = Duration.zero; });
    } catch (e) { setState(() => _error = '$e'); if (was) await _refresh(); }
  }

  @override
  void dispose() {
    _stopTicker();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      backgroundColor: const Color(0xFF0F0F0F),
      body: SafeArea(
        child: _running ? _buildRunning() : _buildIdle(),
      ),
    );
  }

  // ─── Running state ──────────────────────────────────────────────────

  Widget _buildRunning() {
    final color = Color.fromARGB(255, _projectColor[0], _projectColor[1], _projectColor[2]);
    final h = _elapsed.inHours;
    final m = _elapsed.inMinutes.remainder(60);
    final s = _elapsed.inSeconds.remainder(60);

    return GestureDetector(
      onVerticalDragEnd: (_) => _refresh(),
      child: Column(
        children: [
          const SizedBox(height: 16),
          // Top bar: today's total placeholder
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.04),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.local_fire_department, size: 14, color: color.withValues(alpha: 0.7)),
                      const SizedBox(width: 6),
                      Text(
                        'In session',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.white.withValues(alpha: 0.4),
                          letterSpacing: 0.5,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Center: the timepiece
          Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Project name
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 8, height: 8,
                        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        _projectName ?? '',
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                          color: Colors.white.withValues(alpha: 0.6),
                          letterSpacing: 1.5,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 40),

                  // Timer ring
                  AnimatedBuilder(
                    animation: _pulseAnimation,
                    builder: (context, child) {
                      return Container(
                        width: 240, height: 240,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: color.withValues(alpha: 0.15),
                            width: 1,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: color.withValues(alpha: _pulseAnimation.value),
                              blurRadius: 60,
                              spreadRadius: 5,
                            ),
                          ],
                        ),
                        child: CustomPaint(
                          painter: _TimerRingPainter(
                            progress: (s / 60.0),
                            color: color,
                          ),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                // Hours (if any)
                                if (h > 0)
                                  Text(
                                    '$h',
                                    style: TextStyle(
                                      fontSize: 56,
                                      fontWeight: FontWeight.w100,
                                      color: Colors.white.withValues(alpha: 0.9),
                                      height: 1.0,
                                      fontFeatures: [const FontFeature.tabularFigures()],
                                    ),
                                  ),
                                if (h > 0)
                                  Text(
                                    'h ${m.toString().padLeft(2, '0')}m',
                                    style: TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w300,
                                      color: Colors.white.withValues(alpha: 0.4),
                                      letterSpacing: 2,
                                    ),
                                  ),
                                // Minutes:Seconds (no hours)
                                if (h == 0)
                                  Text(
                                    m.toString().padLeft(2, '0'),
                                    style: TextStyle(
                                      fontSize: 64,
                                      fontWeight: FontWeight.w100,
                                      color: Colors.white.withValues(alpha: 0.9),
                                      height: 1.0,
                                      fontFeatures: [const FontFeature.tabularFigures()],
                                    ),
                                  ),
                                if (h == 0)
                                  Text(
                                    s.toString().padLeft(2, '0'),
                                    style: TextStyle(
                                      fontSize: 28,
                                      fontWeight: FontWeight.w200,
                                      color: Colors.white.withValues(alpha: 0.3),
                                      letterSpacing: 4,
                                      fontFeatures: [const FontFeature.tabularFigures()],
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 48),

                  // Stop button
                  GestureDetector(
                    onTap: _stop,
                    child: Container(
                      width: 64, height: 64,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.white.withValues(alpha: 0.06),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                      ),
                      child: Center(
                        child: Container(
                          width: 22, height: 22,
                          decoration: BoxDecoration(
                            color: color,
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'tap to stop',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.white.withValues(alpha: 0.2),
                      letterSpacing: 1,
                    ),
                  ),
                ],
              ),
            ),
          ),

          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 11)),
            ),
        ],
      ),
    );
  }

  // ─── Idle state ─────────────────────────────────────────────────────

  Widget _buildIdle() {
    return RefreshIndicator(
      onRefresh: _refresh,
      color: const Color(0xFFD4952A),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(28, 24, 28, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _greeting(),
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w200,
                      color: Colors.white.withValues(alpha: 0.85),
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Pick a project to begin tracking.',
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.white.withValues(alpha: 0.3),
                    ),
                  ),

                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 11)),
                  ],
                  const SizedBox(height: 32),
                ],
              ),
            ),
          ),

          // Project grid
          if (_projects.isNotEmpty)
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              sliver: SliverGrid(
                delegate: SliverChildBuilderDelegate(
                  (context, i) => _buildProjectCard(_projects[i]),
                  childCount: _projects.length,
                ),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  mainAxisSpacing: 12,
                  crossAxisSpacing: 12,
                  childAspectRatio: 1.4,
                ),
              ),
            ),

          if (_projects.isEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: 60),
                child: Center(
                  child: Column(
                    children: [
                      Icon(Icons.folder_open, size: 40, color: Colors.white.withValues(alpha: 0.1)),
                      const SizedBox(height: 12),
                      Text(
                        'No projects yet',
                        style: TextStyle(color: Colors.white.withValues(alpha: 0.3), fontSize: 14),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Create one in the web dashboard',
                        style: TextStyle(color: Colors.white.withValues(alpha: 0.15), fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildProjectCard(Map<String, dynamic> project) {
    final rgb = (project['color_rgb'] as List?)?.cast<int>() ?? [150, 150, 150];
    final color = Color.fromARGB(255, rgb[0], rgb[1], rgb[2]);
    final name = project['name'] ?? 'Unnamed';

    return GestureDetector(
      onTap: () => _start(project['id'], name, rgb),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: color.withValues(alpha: 0.08),
          border: Border.all(color: color.withValues(alpha: 0.12)),
        ),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                Container(
                  width: 10, height: 10,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                const Spacer(),
                Icon(Icons.play_arrow_rounded, color: color.withValues(alpha: 0.5), size: 22),
              ],
            ),
            Text(
              name,
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w500,
                color: Colors.white.withValues(alpha: 0.8),
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  }
}

// ─── Timer ring painter ─────────────────────────────────────────────

class _TimerRingPainter extends CustomPainter {
  final double progress; // 0..1 for the seconds sweep
  final Color color;
  _TimerRingPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 2;

    // Tick marks (60)
    for (var i = 0; i < 60; i++) {
      final angle = (i / 60) * 2 * pi - pi / 2;
      final isHour = i % 5 == 0;
      final len = isHour ? 8.0 : 4.0;
      final opacity = isHour ? 0.25 : 0.08;
      final start = Offset(
        center.dx + (radius - len) * cos(angle),
        center.dy + (radius - len) * sin(angle),
      );
      final end = Offset(
        center.dx + radius * cos(angle),
        center.dy + radius * sin(angle),
      );
      canvas.drawLine(
        start, end,
        Paint()
          ..color = Colors.white.withValues(alpha: opacity)
          ..strokeWidth = isHour ? 1.5 : 0.8
          ..strokeCap = StrokeCap.round,
      );
    }

    // Progress arc (seconds sweep)
    final sweepAngle = progress * 2 * pi;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius - 12),
      -pi / 2,
      sweepAngle,
      false,
      Paint()
        ..color = color.withValues(alpha: 0.4)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round,
    );

    // Dot at current position
    if (progress > 0) {
      final dotAngle = -pi / 2 + sweepAngle;
      final dotPos = Offset(
        center.dx + (radius - 12) * cos(dotAngle),
        center.dy + (radius - 12) * sin(dotAngle),
      );
      canvas.drawCircle(dotPos, 3, Paint()..color = color);
    }
  }

  @override
  bool shouldRepaint(covariant _TimerRingPainter old) =>
      old.progress != progress || old.color != color;
}
