import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import '../services/api_client.dart';
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

  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this, duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _refresh();
    _syncTimer = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
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
      await widget.client.stopTimer(stopTime: stopTime);
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
    } catch (e) { setState(() => _error = '$e'); if (was) await _refresh(); }
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
  final String? selectedId;
  final void Function(String id, String name, List<int> color) onSelected;
  const _ProjectPickerSheet({required this.projects, this.selectedId, required this.onSelected});

  @override
  State<_ProjectPickerSheet> createState() => _ProjectPickerSheetState();
}

class _ProjectPickerSheetState extends State<_ProjectPickerSheet> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final filtered = _query.isEmpty
        ? widget.projects
        : widget.projects.where((p) =>
            (p['name'] as String? ?? '').toLowerCase().contains(_query.toLowerCase())).toList();

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

          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 360),
            child: filtered.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text('No projects found',
                      style: BeatsType.bodySmall.copyWith(color: BeatsColors.textTertiary)),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: filtered.length,
                    itemBuilder: (_, i) {
                      final p = filtered[i];
                      final rgb = _hexToRgb(p['color'] as String?);
                      final color = Color.fromARGB(255, rgb[0], rgb[1], rgb[2]);
                      final name = p['name'] as String? ?? 'Unnamed';
                      final selected = p['id'] == widget.selectedId;

                      return GestureDetector(
                        onTap: () => widget.onSelected(p['id'], name, rgb),
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
                              Expanded(child: Text(name, style: BeatsType.bodyMedium.copyWith(
                                fontWeight: selected ? FontWeight.w600 : FontWeight.w400))),
                              if (selected)
                                Icon(Icons.check, size: 18, color: BeatsColors.amber),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
}
