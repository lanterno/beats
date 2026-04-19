import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_client.dart';

class TimerScreen extends StatefulWidget {
  final ApiClient client;
  const TimerScreen({super.key, required this.client});

  @override
  State<TimerScreen> createState() => _TimerScreenState();
}

class _TimerScreenState extends State<TimerScreen> {
  bool _loading = true;
  bool _running = false;
  String? _projectName;
  List<int> _projectColor = [212, 149, 42];
  DateTime? _startTime;
  Duration _elapsed = Duration.zero;
  Timer? _ticker;
  String? _error;

  // Projects for picker
  List<Map<String, dynamic>> _projects = [];

  @override
  void initState() {
    super.initState();
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
      if (mounted) {
        setState(() {
          _error = '$e';
          _loading = false;
        });
      }
    }
  }

  void _startTicker() {
    _stopTicker();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_startTime != null && mounted) {
        setState(() {
          _elapsed = DateTime.now().toUtc().difference(_startTime!);
        });
      }
    });
  }

  void _stopTicker() {
    _ticker?.cancel();
    _ticker = null;
  }

  Future<void> _start(String projectId, String projectName, List<int> color) async {
    setState(() {
      _running = true;
      _projectName = projectName;
      _projectColor = color;
      _startTime = DateTime.now().toUtc();
      _elapsed = Duration.zero;
      _error = null;
    });
    _startTicker();

    try {
      await widget.client.startTimer(projectId);
    } catch (e) {
      setState(() => _error = '$e');
      await _refresh();
    }
  }

  Future<void> _stop() async {
    _stopTicker();
    final wasRunning = _running;
    setState(() {
      _running = false;
      _error = null;
    });

    try {
      await widget.client.stopTimer();
      setState(() {
        _projectName = null;
        _startTime = null;
        _elapsed = Duration.zero;
      });
    } catch (e) {
      setState(() => _error = '$e');
      if (wasRunning) await _refresh();
    }
  }

  String _formatDuration(Duration d) {
    final h = d.inHours;
    final m = d.inMinutes.remainder(60);
    final s = d.inSeconds.remainder(60);
    if (h > 0) return '${h}h ${m.toString().padLeft(2, '0')}m ${s.toString().padLeft(2, '0')}s';
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  @override
  void dispose() {
    _stopTicker();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_running) {
      return _buildRunningState(theme);
    }

    return _buildIdleState(theme);
  }

  Widget _buildRunningState(ThemeData theme) {
    final color = Color.fromARGB(255, _projectColor[0], _projectColor[1], _projectColor[2]);

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 48),
        children: [
          // Project indicator
          Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 12,
                  height: 12,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                const SizedBox(width: 10),
                Text(
                  _projectName ?? 'Working',
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 48),

          // Elapsed time
          Center(
            child: Text(
              _formatDuration(_elapsed),
              style: theme.textTheme.displayLarge?.copyWith(
                fontWeight: FontWeight.w200,
                letterSpacing: 4,
                fontFeatures: [const FontFeature.tabularFigures()],
              ),
            ),
          ),
          const SizedBox(height: 48),

          // Stop button
          Center(
            child: SizedBox(
              width: 80,
              height: 80,
              child: FilledButton(
                onPressed: _stop,
                style: FilledButton.styleFrom(
                  backgroundColor: theme.colorScheme.error,
                  shape: const CircleBorder(),
                ),
                child: Icon(Icons.stop, size: 36, color: theme.colorScheme.onError),
              ),
            ),
          ),

          if (_error != null) ...[
            const SizedBox(height: 24),
            Text(_error!, style: TextStyle(color: theme.colorScheme.error, fontSize: 12), textAlign: TextAlign.center),
          ],
        ],
      ),
    );
  }

  Widget _buildIdleState(ThemeData theme) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        children: [
          Center(
            child: Text(
              'What are you working on?',
              style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w300),
            ),
          ),
          const SizedBox(height: 32),

          if (_error != null) ...[
            Text(_error!, style: TextStyle(color: theme.colorScheme.error, fontSize: 12), textAlign: TextAlign.center),
            const SizedBox(height: 16),
          ],

          // Project list
          ..._projects.map((p) {
            final rgb = (p['color_rgb'] as List?)?.cast<int>() ?? [150, 150, 150];
            final color = Color.fromARGB(255, rgb[0], rgb[1], rgb[2]);

            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Card(
                child: ListTile(
                  leading: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(Icons.play_arrow, color: color),
                  ),
                  title: Text(p['name'] ?? 'Unnamed'),
                  onTap: () => _start(p['id'], p['name'], rgb),
                ),
              ),
            );
          }),

          if (_projects.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.only(top: 32),
                child: Text(
                  'No projects yet. Create one in the web UI.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
