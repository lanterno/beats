import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import '../services/api_client.dart';
import '../services/recent_projects.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

List<int> _hexToRgb(String? hex) {
  if (hex == null || hex.isEmpty) return [150, 150, 150];
  hex = hex.replaceFirst('#', '');
  if (hex.length != 6) return [150, 150, 150];
  return [
    int.parse(hex.substring(0, 2), radix: 16),
    int.parse(hex.substring(2, 4), radix: 16),
    int.parse(hex.substring(4, 6), radix: 16),
  ];
}

class TimerScreen extends StatefulWidget {
  final ApiClient client;
  const TimerScreen({super.key, required this.client});

  @override
  State<TimerScreen> createState() => _TimerScreenState();
}

class _TimerScreenState extends State<TimerScreen> with SingleTickerProviderStateMixin {
  bool _loading = true;
  bool _running = false;
  String? _selectedProjectId;
  String? _selectedProjectName;
  List<int> _selectedProjectColor = [212, 149, 42];
  DateTime? _startTime;
  Duration _elapsed = Duration.zero;
  Timer? _ticker;
  Timer? _syncTimer;
  String? _error;
  List<Map<String, dynamic>> _projects = [];
  bool _showStartTimeInput = false;
  bool _showStopTimeInput = false;
  DateTime? _customStartTime;
  DateTime? _customStopTime;

  final RecentProjects _recents = RecentProjects();
  List<String> _recentIds = const [];

  // Stats row (today, this week, current streak) computed from the heatmap.
  int _todayMinutes = 0;
  int _weekMinutes = 0;
  int _streakDays = 0;
  bool _statsLoaded = false;

  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this, duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _refresh();
    _refreshStats();
    _loadRecents();
    _syncTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _refresh();
      _refreshStats();
    });
  }

  Future<void> _loadRecents() async {
    final ids = await _recents.load();
    if (!mounted) return;
    setState(() => _recentIds = ids);
  }

  Future<void> _refresh() async {
    try {
      final status = await widget.client.getTimerStatus();
      final projects = await widget.client.getProjects();
      if (mounted) {
        setState(() {
          _projects = projects;
          final isBeating = status['isBeating'] == true;
          _error = null;
          if (isBeating && status['since'] != null) {
            final project = status['project'] as Map<String, dynamic>?;
            _running = true;
            _selectedProjectId = project?['id'];
            _selectedProjectName = project?['name'] ?? _selectedProjectId;
            _startTime = DateTime.parse(status['since']);
            _elapsed = DateTime.now().toUtc().difference(_startTime!);
            final proj = projects.where((p) => p['id'] == _selectedProjectId).firstOrNull;
            if (proj != null) _selectedProjectColor = _hexToRgb(proj['color'] as String?);
            _startTicker();
          } else {
            _running = false;
            _stopTicker();
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

  Future<void> _refreshStats() async {
    try {
      final today = DateTime.now();
      final entries = await widget.client.getHeatmap(year: today.year);
      // The heatmap is keyed by 'YYYY-MM-DD' strings — index it for O(1) lookup.
      final byDate = <String, int>{
        for (final e in entries)
          if (e['date'] is String) e['date'] as String: (e['total_minutes'] as num?)?.toInt() ?? 0,
      };

      final todayKey = _dateKey(today);
      final todayMins = byDate[todayKey] ?? 0;

      // Week = Monday→Sunday containing today (DateTime.weekday: Mon=1, Sun=7).
      final weekStart = DateTime(today.year, today.month, today.day)
          .subtract(Duration(days: today.weekday - 1));
      var weekMins = 0;
      for (var i = 0; i < 7; i++) {
        weekMins += byDate[_dateKey(weekStart.add(Duration(days: i)))] ?? 0;
      }

      // Streak: walk back day-by-day, counting consecutive days with minutes > 0.
      // Today is forgiven if it has zero minutes (so the streak doesn't drop until
      // the user has actually missed a day).
      var streak = 0;
      var cursor = DateTime(today.year, today.month, today.day);
      var first = true;
      while (true) {
        final mins = byDate[_dateKey(cursor)] ?? 0;
        if (mins > 0) {
          streak++;
        } else if (!first) {
          break;
        }
        first = false;
        cursor = cursor.subtract(const Duration(days: 1));
        // Bound the walk to a year to avoid runaway loops on garbage data.
        if (today.difference(cursor).inDays > 365) break;
      }

      if (!mounted) return;
      setState(() {
        _todayMinutes = todayMins;
        _weekMinutes = weekMins;
        _streakDays = streak;
        _statsLoaded = true;
      });
    } catch (_) {
      // Stats are non-critical — leave them stale on transient failures.
    }
  }

  String _dateKey(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  String _formatMinutes(int minutes) {
    if (minutes <= 0) return '0m';
    final h = minutes ~/ 60;
    final m = minutes % 60;
    if (h == 0) return '${m}m';
    if (m == 0) return '${h}h';
    return '${h}h ${m}m';
  }

  Future<void> _handleStart() async {
    if (_selectedProjectId == null) return;
    final startTime = _showStartTimeInput && _customStartTime != null
        ? _customStartTime!.toUtc().toIso8601String() : null;
    setState(() {
      _running = true;
      _startTime = _customStartTime?.toUtc() ?? DateTime.now().toUtc();
      _elapsed = DateTime.now().toUtc().difference(_startTime!);
      _error = null;
      _showStartTimeInput = false;
    });
    _startTicker();
    try {
      await widget.client.startTimer(_selectedProjectId!, startTime: startTime);
      // Promote this project to the head of the recents list — used by the
      // picker to surface a "RECENT" section.
      final id = _selectedProjectId;
      if (id != null) {
        await _recents.markUsed(id);
        await _loadRecents();
      }
      await _refresh();
    } catch (e) { setState(() => _error = '$e'); await _refresh(); }
  }

  Future<void> _handleStop() async {
    _stopTicker();
    final projectName = _selectedProjectName ?? '';
    final minutes = _elapsed.inMinutes;
    final was = _running;
    final stopTime = _showStopTimeInput && _customStopTime != null
        ? _customStopTime!.toUtc().toIso8601String() : null;
    setState(() {
      _running = false; _error = null;
      _showStopTimeInput = false; _customStopTime = null; _customStartTime = null;
    });
    try {
      final beat = await widget.client.stopTimer(stopTime: stopTime);
      setState(() { _startTime = null; _elapsed = Duration.zero; });
      if (mounted && projectName.isNotEmpty) {
        final dur = minutes >= 60 ? '${minutes ~/ 60}h ${minutes % 60}m' : '${minutes}m';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Row(children: [
            Container(width: 10, height: 10, decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Color.fromARGB(255, _selectedProjectColor[0], _selectedProjectColor[1], _selectedProjectColor[2]),
            )),
            const SizedBox(width: 10),
            Text('$dur logged to $projectName', style: BeatsType.bodyMedium),
          ]),
          backgroundColor: BeatsColors.surfaceAlt,
          behavior: SnackBarBehavior.floating,
        ));
      }
      await _refresh();
      await _refreshStats();
      // Prompt for an optional note + tags on the just-stopped session.
      // Skipped sessions still log the time; this is purely additive context.
      if (mounted && beat['id'] != null) {
        unawaited(_promptPostStopNote(beat));
      }
    } catch (e) { setState(() => _error = '$e'); if (was) await _refresh(); }
  }

  Future<void> _promptPostStopNote(Map<String, dynamic> beat) async {
    final result = await showModalBottomSheet<_PostStopResult?>(
      context: context,
      backgroundColor: BeatsColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _PostStopSheet(projectName: _selectedProjectName ?? ''),
    );
    if (result == null) return; // skipped
    final updated = Map<String, dynamic>.from(beat)
      ..['note'] = result.note
      ..['tags'] = result.tags;
    try {
      await widget.client.updateBeat(updated);
    } catch (_) {
      // Best-effort: the session is already saved; surface a snackbar but
      // don't roll back the UI.
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Couldn\'t save your note — try editing the session later'),
        behavior: SnackBarBehavior.floating,
      ));
    }
  }

  void _showProjectPicker() {
    showModalBottomSheet(
      context: context,
      backgroundColor: BeatsColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _ProjectPickerSheet(
        projects: _projects,
        recentIds: _recentIds,
        selectedId: _selectedProjectId,
        onSelected: (id, name, color) {
          setState(() {
            _selectedProjectId = id;
            _selectedProjectName = name;
            _selectedProjectColor = color;
          });
          Navigator.pop(ctx);
        },
      ),
    );
  }

  @override
  void dispose() {
    _stopTicker(); _syncTimer?.cancel(); _pulseController.dispose();
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

    final projColor = Color.fromARGB(
        255, _selectedProjectColor[0], _selectedProjectColor[1], _selectedProjectColor[2]);

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: Container(
        decoration: _running
            ? BoxDecoration(
                gradient: RadialGradient(
                  center: const Alignment(0, -0.5),
                  radius: 1.5,
                  colors: [
                    projColor.withValues(alpha: 0.07),
                    BeatsColors.background,
                  ],
                ),
              )
            : null,
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: _refresh,
            color: BeatsColors.amber,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(24, 16, 24, 100),
              children: [
                // ── Status chip ──
                StaggeredEntrance(
                  child: Center(
                    child: _running
                        ? _buildRunningChip(projColor)
                        : Text(_greeting(),
                            style: GoogleFonts.dmSerifDisplay(
                              fontSize: 22, color: BeatsColors.textSecondary,
                            )),
                  ),
                ),
                SizedBox(height: _running ? 40 : 48),

                // ── The Time ──
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 60),
                  child: _buildTimeDisplay(),
                ),

                // ── Project name (running) ──
                if (_running) ...[
                  const SizedBox(height: 12),
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 100),
                    child: Center(
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(width: 8, height: 8,
                            decoration: BoxDecoration(shape: BoxShape.circle, color: projColor)),
                          const SizedBox(width: 10),
                          Text(_selectedProjectName ?? '',
                            style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textSecondary)),
                        ],
                      ),
                    ),
                  ),
                  if (_startTime != null) ...[
                    const SizedBox(height: 4),
                    Center(
                      child: Text(
                        'since ${DateFormat.jm().format(_startTime!.toLocal())}',
                        style: BeatsType.bodySmall.copyWith(
                          color: BeatsColors.textTertiary, fontSize: 11),
                      ),
                    ),
                  ],
                ],

                SizedBox(height: _running ? 48 : 32),

                // ── Action area ──
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 120),
                  child: _running ? _buildStopSection() : _buildStartSection(),
                ),

                // ── Stats row (today / week / streak) ──
                if (_statsLoaded) ...[
                  const SizedBox(height: 40),
                  StaggeredEntrance(
                    delay: const Duration(milliseconds: 180),
                    child: _buildStatsRow(),
                  ),
                ],

                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Text(_error!, style: const TextStyle(
                      color: BeatsColors.red, fontSize: 11), textAlign: TextAlign.center),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRunningChip(Color projColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: projColor.withValues(alpha: 0.1),
        border: Border.all(color: projColor.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedBuilder(
            animation: _pulseController,
            builder: (_, _) => Container(
              width: 6, height: 6,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: projColor.withValues(alpha: 0.3 + _pulseController.value * 0.7),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text('RECORDING', style: BeatsType.label.copyWith(
            color: projColor, letterSpacing: 2)),
        ],
      ),
    );
  }

  Widget _buildStatsRow() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        children: [
          Expanded(child: _statCell(label: 'TODAY', value: _formatMinutes(_todayMinutes))),
          _statDivider(),
          Expanded(child: _statCell(label: 'WEEK', value: _formatMinutes(_weekMinutes))),
          _statDivider(),
          Expanded(
            child: _statCell(
              label: 'STREAK',
              value: _streakDays > 0 ? '$_streakDays${_streakDays == 1 ? ' DAY' : ' DAYS'}' : '—',
              accent: _streakDays > 0,
            ),
          ),
        ],
      ),
    );
  }

  Widget _statCell({required String label, required String value, bool accent = false}) {
    return Column(
      children: [
        Text(
          value,
          style: GoogleFonts.jetBrainsMono(
            fontSize: 16,
            fontWeight: FontWeight.w300,
            color: accent ? BeatsColors.amber : BeatsColors.textPrimary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          label,
          style: BeatsType.label.copyWith(
            fontSize: 9,
            color: BeatsColors.textTertiary,
            letterSpacing: 2,
          ),
        ),
      ],
    );
  }

  Widget _statDivider() {
    return Container(
      width: 1,
      height: 32,
      color: BeatsColors.border.withValues(alpha: 0.5),
    );
  }

  Widget _buildTimeDisplay() {
    final h = _elapsed.inHours;
    final m = _elapsed.inMinutes.remainder(60);
    final s = _elapsed.inSeconds.remainder(60);

    final color = _running ? BeatsColors.textPrimary : BeatsColors.textTertiary;
    final colonColor = _running
        ? BeatsColors.textPrimary.withValues(alpha: 0.3)
        : BeatsColors.textTertiary.withValues(alpha: 0.3);

    // Massive brutalist time display
    return Center(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          // Hours
          _TimeUnit(value: h.toString().padLeft(2, '0'), label: 'HR', color: color),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(':', style: GoogleFonts.jetBrainsMono(
              fontSize: 56, fontWeight: FontWeight.w100, color: colonColor)),
          ),
          // Minutes
          _TimeUnit(value: m.toString().padLeft(2, '0'), label: 'MIN', color: color),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(':', style: GoogleFonts.jetBrainsMono(
              fontSize: 56, fontWeight: FontWeight.w100, color: colonColor)),
          ),
          // Seconds
          _TimeUnit(value: s.toString().padLeft(2, '0'), label: 'SEC',
            color: _running
                ? BeatsColors.textPrimary.withValues(alpha: 0.4)
                : BeatsColors.textTertiary.withValues(alpha: 0.4)),
        ],
      ),
    );
  }

  Widget _buildStartSection() {
    return Column(
      children: [
        // Project selector
        GestureDetector(
          onTap: _showProjectPicker,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: BeatsColors.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: BeatsColors.border),
            ),
            child: Row(
              children: [
                if (_selectedProjectId != null) ...[
                  Container(width: 10, height: 10, decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Color.fromARGB(255, _selectedProjectColor[0],
                        _selectedProjectColor[1], _selectedProjectColor[2]),
                  )),
                  const SizedBox(width: 12),
                  Expanded(child: Text(_selectedProjectName ?? '',
                    style: BeatsType.bodyMedium)),
                ] else ...[
                  Icon(Icons.search, size: 18, color: BeatsColors.textTertiary),
                  const SizedBox(width: 12),
                  Expanded(child: Text('Select a project...',
                    style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary))),
                ],
                Icon(Icons.unfold_more, size: 18, color: BeatsColors.textTertiary),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),

        // Start button
        GestureDetector(
          onTap: _selectedProjectId != null ? _handleStart : null,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(
              color: _selectedProjectId != null
                  ? BeatsColors.amber
                  : BeatsColors.textTertiary.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text('Start',
                style: BeatsType.button.copyWith(
                  fontSize: 16,
                  color: _selectedProjectId != null
                      ? const Color(0xFF1A1408)
                      : BeatsColors.textTertiary,
                )),
            ),
          ),
        ),

        // Custom start time
        if (_selectedProjectId != null) ...[
          const SizedBox(height: 10),
          GestureDetector(
            onTap: () => setState(() {
              _showStartTimeInput = !_showStartTimeInput;
              if (_showStartTimeInput && _customStartTime == null) {
                _customStartTime = DateTime.now().subtract(const Duration(hours: 1));
              }
            }),
            child: Text(
              _showStartTimeInput ? 'Hide start time' : 'Set start time',
              style: BeatsType.bodySmall.copyWith(
                color: _showStartTimeInput ? BeatsColors.amber : BeatsColors.textTertiary,
              ),
            ),
          ),
          if (_showStartTimeInput) ...[
            const SizedBox(height: 12),
            _DateTimePicker(
              value: _customStartTime ?? DateTime.now().subtract(const Duration(hours: 1)),
              onChanged: (dt) => setState(() => _customStartTime = dt),
            ),
          ],
        ],
      ],
    );
  }

  Widget _buildStopSection() {
    return Column(
      children: [
        // Stop button
        GestureDetector(
          onTap: _handleStop,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(
              color: BeatsColors.red,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(width: 14, height: 14,
                  decoration: BoxDecoration(
                    color: Colors.white, borderRadius: BorderRadius.circular(2))),
                const SizedBox(width: 10),
                Text('Stop', style: BeatsType.button.copyWith(
                  fontSize: 16, color: Colors.white)),
              ],
            ),
          ),
        ),

        // Custom stop time
        const SizedBox(height: 10),
        GestureDetector(
          onTap: () => setState(() {
            _showStopTimeInput = !_showStopTimeInput;
            if (_showStopTimeInput && _customStopTime == null) {
              _customStopTime = DateTime.now();
            }
          }),
          child: Text(
            _showStopTimeInput ? 'Hide stop time' : 'Set stop time',
            style: BeatsType.bodySmall.copyWith(
              color: _showStopTimeInput ? BeatsColors.amber : BeatsColors.textTertiary),
          ),
        ),
        if (_showStopTimeInput) ...[
          const SizedBox(height: 12),
          _DateTimePicker(
            value: _customStopTime ?? DateTime.now(),
            onChanged: (dt) => setState(() => _customStopTime = dt),
          ),
        ],
      ],
    );
  }

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }
}

// ─── Time unit with label ───────────────────────────────────────────

class _TimeUnit extends StatelessWidget {
  final String value;
  final String label;
  final Color color;
  const _TimeUnit({required this.value, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(value,
          style: GoogleFonts.jetBrainsMono(
            fontSize: 64, fontWeight: FontWeight.w200, color: color, height: 1,
            fontFeatures: [const FontFeature.tabularFigures()],
          )),
        const SizedBox(height: 4),
        Text(label, style: BeatsType.label.copyWith(
          fontSize: 9, color: color.withValues(alpha: 0.4), letterSpacing: 3)),
      ],
    );
  }
}

// ─── DateTime Picker ────────────────────────────────────────────────

class _DateTimePicker extends StatelessWidget {
  final DateTime value;
  final ValueChanged<DateTime> onChanged;
  const _DateTimePicker({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        final date = await showDatePicker(
          context: context, initialDate: value,
          firstDate: DateTime.now().subtract(const Duration(days: 7)),
          lastDate: DateTime.now().add(const Duration(days: 1)),
        );
        if (date == null || !context.mounted) return;
        final time = await showTimePicker(
          context: context, initialTime: TimeOfDay.fromDateTime(value),
        );
        if (time == null) return;
        onChanged(DateTime(date.year, date.month, date.day, time.hour, time.minute));
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: BeatsColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: BeatsColors.border),
        ),
        child: Row(
          children: [
            Icon(Icons.schedule, size: 16, color: BeatsColors.textTertiary),
            const SizedBox(width: 10),
            Text(DateFormat('MMM d, h:mm a').format(value),
              style: BeatsType.bodyMedium),
          ],
        ),
      ),
    );
  }
}

// ─── Project Picker Sheet ───────────────────────────────────────────

class _ProjectPickerSheet extends StatefulWidget {
  final List<Map<String, dynamic>> projects;
  final List<String> recentIds;
  final String? selectedId;
  final void Function(String id, String name, List<int> color) onSelected;
  const _ProjectPickerSheet({
    required this.projects,
    this.recentIds = const [],
    this.selectedId,
    required this.onSelected,
  });

  @override
  State<_ProjectPickerSheet> createState() => _ProjectPickerSheetState();
}

class _ProjectPickerSheetState extends State<_ProjectPickerSheet> {
  String _query = '';

  /// Map of id → project, for O(1) lookup when resolving recents.
  Map<String, Map<String, dynamic>> _projectsById() => {
        for (final p in widget.projects)
          if (p['id'] is String) p['id'] as String: p,
      };

  @override
  Widget build(BuildContext context) {
    final all = widget.projects;
    final filtered = _query.isEmpty
        ? all
        : all.where((p) =>
            (p['name'] as String? ?? '').toLowerCase().contains(_query.toLowerCase())).toList();

    // Resolve recents to actual project records (only show recents that still
    // exist + aren't already filtered out by the search query).
    final byId = _projectsById();
    final recents = _query.isNotEmpty
        ? const <Map<String, dynamic>>[]
        : widget.recentIds
            .map((id) => byId[id])
            .whereType<Map<String, dynamic>>()
            .toList(growable: false);
    final recentIdSet = {for (final r in recents) r['id'] as String?};

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 12),
          Container(width: 40, height: 4, decoration: BoxDecoration(
            color: BeatsColors.textTertiary.withValues(alpha: 0.2),
            borderRadius: BorderRadius.circular(2))),
          const SizedBox(height: 20),

          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: TextField(
              autofocus: true,
              onChanged: (v) => setState(() => _query = v),
              style: BeatsType.bodyMedium,
              decoration: InputDecoration(
                hintText: 'Search projects...',
                hintStyle: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary),
                prefixIcon: Icon(Icons.search, size: 20, color: BeatsColors.textTertiary),
                filled: true,
                fillColor: BeatsColors.background,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: BeatsColors.border)),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: BeatsColors.border)),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: BeatsColors.amber.withValues(alpha: 0.4))),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              ),
            ),
          ),
          const SizedBox(height: 8),

          // Spring entrance for the list area: scale from 0.97 → 1.0 with an
          // easeOutBack curve so it feels like the content settles into place.
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 420),
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0.0, end: 1.0),
              duration: const Duration(milliseconds: 320),
              curve: Curves.easeOutBack,
              builder: (_, t, child) {
                final clamped = t.clamp(0.0, 1.0);
                return Opacity(
                  opacity: clamped,
                  child: Transform.scale(
                    scale: 0.97 + 0.03 * clamped,
                    alignment: Alignment.topCenter,
                    child: child,
                  ),
                );
              },
              child: filtered.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text('No projects found',
                        style: BeatsType.bodySmall.copyWith(color: BeatsColors.textTertiary)),
                    )
                  : ListView(
                      shrinkWrap: true,
                      children: [
                        if (recents.isNotEmpty) ...[
                          _sectionLabel('RECENT'),
                          for (final p in recents) _projectRow(p),
                          const SizedBox(height: 12),
                          _sectionLabel('ALL PROJECTS'),
                        ],
                        for (final p in filtered)
                          if (recentIdSet.contains(p['id']) && _query.isEmpty)
                            const SizedBox.shrink()
                          else
                            _projectRow(p),
                      ],
                    ),
            ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _sectionLabel(String text) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 6),
      child: Text(
        text,
        style: BeatsType.label.copyWith(
          fontSize: 9,
          letterSpacing: 2,
          color: BeatsColors.textTertiary,
        ),
      ),
    );
  }

  Widget _projectRow(Map<String, dynamic> p) {
    final rgb = _hexToRgb(p['color'] as String?);
    final color = Color.fromARGB(255, rgb[0], rgb[1], rgb[2]);
    final name = p['name'] as String? ?? 'Unnamed';
    final id = p['id'] as String? ?? '';
    final selected = id == widget.selectedId;

    return GestureDetector(
      onTap: () => widget.onSelected(id, name, rgb),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: selected ? BeatsColors.amber.withValues(alpha: 0.08) : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Container(
              width: 4, height: 24,
              decoration: BoxDecoration(
                color: color, borderRadius: BorderRadius.circular(2))),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                name,
                style: BeatsType.bodyMedium.copyWith(
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ),
            if (selected)
              Icon(Icons.check, size: 18, color: BeatsColors.amber),
          ],
        ),
      ),
    );
  }
}

// ─── Post-stop "How did it go?" sheet ───────────────────────────────

class _PostStopResult {
  final String note;
  final List<String> tags;
  const _PostStopResult({required this.note, required this.tags});
}

class _PostStopSheet extends StatefulWidget {
  final String projectName;
  const _PostStopSheet({required this.projectName});

  @override
  State<_PostStopSheet> createState() => _PostStopSheetState();
}

class _PostStopSheetState extends State<_PostStopSheet> {
  final _noteController = TextEditingController();
  final _tagsController = TextEditingController();

  @override
  void dispose() {
    _noteController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  List<String> _parseTags(String raw) =>
      raw.split(RegExp(r'[,\s]+'))
          .map((t) => t.trim().toLowerCase())
          .where((t) => t.isNotEmpty)
          .toSet()
          .toList();

  void _save() {
    Navigator.pop(
      context,
      _PostStopResult(
        note: _noteController.text.trim(),
        tags: _parseTags(_tagsController.text),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(child: Container(width: 40, height: 4, decoration: BoxDecoration(
              color: BeatsColors.textTertiary.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(2)))),
            const SizedBox(height: 20),
            Text(
              widget.projectName.isEmpty
                  ? 'How did it go?'
                  : 'How did it go on ${widget.projectName}?',
              style: GoogleFonts.dmSerifDisplay(
                fontSize: 22, color: BeatsColors.textPrimary),
            ),
            const SizedBox(height: 16),
            Text('NOTE', style: BeatsType.label),
            const SizedBox(height: 6),
            TextField(
              controller: _noteController,
              autofocus: true,
              maxLines: null,
              minLines: 3,
              style: BeatsType.bodyMedium,
              cursorColor: BeatsColors.amber,
              decoration: _decoration('A line about how it went…'),
            ),
            const SizedBox(height: 16),
            Text('TAGS', style: BeatsType.label),
            const SizedBox(height: 6),
            TextField(
              controller: _tagsController,
              style: BeatsType.bodyMedium,
              cursorColor: BeatsColors.amber,
              decoration: _decoration('comma, separated, words'),
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _save(),
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: GestureDetector(
                    onTap: () => Navigator.pop(context, null),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: BeatsColors.border),
                      ),
                      child: Text('Skip', style: BeatsType.button.copyWith(
                        color: BeatsColors.textTertiary)),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: GestureDetector(
                    onTap: _save,
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: BeatsColors.amber,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text('Save', style: BeatsType.button.copyWith(
                        color: const Color(0xFF1A1408))),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _decoration(String hint) => InputDecoration(
    hintText: hint,
    hintStyle: BeatsType.bodyMedium.copyWith(
      color: BeatsColors.textTertiary.withValues(alpha: 0.5)),
    isDense: true,
    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: BorderSide(color: BeatsColors.border)),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: BorderSide(color: BeatsColors.amber.withValues(alpha: 0.6))),
  );
}
