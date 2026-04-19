import 'dart:async';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../services/api_client.dart';

// Beats ember theme (matching web hsl values)
const _bgColor = Color(0xFF161210); // hsl(25 15% 8%)
const _cardColor = Color(0xFF1F1B15); // hsl(25 12% 11%)
const _cardRunning = Color(0xFF1E1A11); // bg-accent/5
const _borderColor = Color(0xFF2E2A23);
const _accent = Color(0xFFD4952A); // hsl(38 80% 52%)
const _destructive = Color(0xFFBF4040); // hsl(0 55% 50%)
const _mutedFg = Color(0xFF8A7E6E);
const _labelColor = Color(0xFF6B6155); // muted-foreground for labels

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
  String? _error;
  List<Map<String, dynamic>> _projects = [];

  // Custom time inputs
  bool _showStartTimeInput = false;
  bool _showStopTimeInput = false;
  DateTime? _customStartTime;
  DateTime? _customStopTime;

  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
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
            _selectedProjectId = beat['project_id'];
            _selectedProjectName = status['project_name'] ?? beat['project_id'];
            _startTime = DateTime.parse(beat['start']);
            _elapsed = DateTime.now().toUtc().difference(_startTime!);
            // Find project color
            final proj = projects.where((p) => p['id'] == _selectedProjectId).firstOrNull;
            if (proj != null) {
              final rgb = (proj['color_rgb'] as List?)?.cast<int>() ?? [212, 149, 42];
              _selectedProjectColor = rgb;
            }
            _startTicker();
          } else {
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
    setState(() {
      _running = true;
      _startTime = _customStartTime ?? DateTime.now().toUtc();
      _elapsed = DateTime.now().toUtc().difference(_startTime!);
      _error = null;
      _showStartTimeInput = false;
    });
    _startTicker();
    try { await widget.client.startTimer(_selectedProjectId!); }
    catch (e) { setState(() => _error = '$e'); await _refresh(); }
  }

  Future<void> _handleStop() async {
    _stopTicker();
    final projectName = _selectedProjectName ?? '';
    final minutes = _elapsed.inMinutes;
    final was = _running;
    setState(() {
      _running = false;
      _error = null;
      _showStopTimeInput = false;
      _customStopTime = null;
      _customStartTime = null;
    });
    try {
      await widget.client.stopTimer();
      setState(() { _startTime = null; _elapsed = Duration.zero; });
      if (mounted && projectName.isNotEmpty) {
        final dur = minutes >= 60
            ? '${minutes ~/ 60}h ${minutes % 60}m'
            : '${minutes}m';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                Container(
                  width: 10, height: 10,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Color.fromARGB(255, _selectedProjectColor[0], _selectedProjectColor[1], _selectedProjectColor[2]),
                  ),
                ),
                const SizedBox(width: 10),
                Text('$dur logged to $projectName'),
              ],
            ),
            backgroundColor: _cardColor,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) { setState(() => _error = '$e'); if (was) await _refresh(); }
  }

  void _showProjectPicker() {
    showModalBottomSheet(
      context: context,
      backgroundColor: _cardColor,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
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

  String _formatDigits(Duration d) {
    final h = d.inHours.toString().padLeft(2, '0');
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$h:$m:$s';
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
      return const Scaffold(
        backgroundColor: _bgColor,
        body: Center(child: CircularProgressIndicator(color: _accent)),
      );
    }

    return Scaffold(
      backgroundColor: _bgColor,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          color: _accent,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 24),
            children: [
              // ── Timer Card ──
              _buildTimerCard(),
              const SizedBox(height: 16),
              // ── Stats Row ──
              _buildStatsRow(),

              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(_error!, style: const TextStyle(color: _destructive, fontSize: 11), textAlign: TextAlign.center),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTimerCard() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeOut,
      decoration: BoxDecoration(
        color: _running ? _cardRunning : _cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: _running ? _accent.withValues(alpha: 0.3) : _borderColor,
        ),
        boxShadow: _running
            ? [BoxShadow(color: _accent.withValues(alpha: 0.15), blurRadius: 20, spreadRadius: -4)]
            : [],
      ),
      child: Stack(
        children: [
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // ── PROJECT section ──
                if (!_running) ...[
                  const _SectionLabel(text: 'PROJECT'),
                  const SizedBox(height: 8),
                  _buildProjectSelector(),
                  const SizedBox(height: 16),
                  Divider(height: 1, color: _borderColor.withValues(alpha: 0.5)),
                  const SizedBox(height: 16),
                ],

                // ── TIMER section ──
                const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.access_time, size: 14, color: _labelColor),
                    SizedBox(width: 6),
                    _SectionLabel(text: 'TIMER'),
                  ],
                ),
                const SizedBox(height: 8),

                // Digits
                Center(
                  child: Text(
                    _formatDigits(_elapsed),
                    style: TextStyle(
                      fontFamily: 'JetBrains Mono',
                      fontFamilyFallback: const ['monospace', 'Courier'],
                      fontSize: 40,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 1,
                      color: _running ? _accent : Colors.white.withValues(alpha: 0.85),
                      fontFeatures: [const FontFeature.tabularFigures()],
                    ),
                  ),
                ),

                // Project name + started time (when running)
                if (_running) ...[
                  const SizedBox(height: 6),
                  Center(
                    child: Text(
                      _selectedProjectName ?? '',
                      style: TextStyle(fontSize: 14, color: _mutedFg),
                    ),
                  ),
                  if (_startTime != null)
                    Center(
                      child: Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          'Started ${DateFormat.jms().format(_startTime!.toLocal())}',
                          style: TextStyle(fontSize: 12, color: _mutedFg.withValues(alpha: 0.6)),
                        ),
                      ),
                    ),
                ],
                const SizedBox(height: 20),

                // ── Buttons ──
                Row(
                  children: [
                    // Start
                    Expanded(
                      child: _TimerButton(
                        label: 'Start',
                        icon: Icons.play_arrow_rounded,
                        color: (_selectedProjectId != null && !_running) ? _accent : _mutedFg.withValues(alpha: 0.2),
                        textColor: (_selectedProjectId != null && !_running) ? const Color(0xFF1A1408) : _mutedFg.withValues(alpha: 0.5),
                        enabled: _selectedProjectId != null && !_running,
                        onTap: _handleStart,
                      ),
                    ),
                    const SizedBox(width: 10),
                    // Stop
                    Expanded(
                      child: _TimerButton(
                        label: 'Stop',
                        icon: Icons.stop_rounded,
                        color: _running ? _destructive : _mutedFg.withValues(alpha: 0.2),
                        textColor: _running ? Colors.white : _mutedFg.withValues(alpha: 0.5),
                        enabled: _running,
                        onTap: _handleStop,
                      ),
                    ),
                  ],
                ),

                // ── Custom time toggles ──
                if (_selectedProjectId != null && !_running) ...[
                  const SizedBox(height: 8),
                  _CustomTimeToggle(
                    label: _showStartTimeInput ? 'Hide start time' : 'Set start time',
                    active: _showStartTimeInput,
                    onTap: () {
                      setState(() {
                        _showStartTimeInput = !_showStartTimeInput;
                        if (_showStartTimeInput && _customStartTime == null) {
                          _customStartTime = DateTime.now().subtract(const Duration(hours: 1));
                        }
                      });
                    },
                  ),
                ],
                if (_running) ...[
                  const SizedBox(height: 8),
                  _CustomTimeToggle(
                    label: _showStopTimeInput ? 'Hide stop time' : 'Set stop time',
                    active: _showStopTimeInput,
                    onTap: () {
                      setState(() {
                        _showStopTimeInput = !_showStopTimeInput;
                        if (_showStopTimeInput && _customStopTime == null) {
                          _customStopTime = DateTime.now();
                        }
                      });
                    },
                  ),
                ],

                // ── Custom start time input ──
                if (_showStartTimeInput && !_running) ...[
                  const SizedBox(height: 12),
                  Divider(height: 1, color: _borderColor.withValues(alpha: 0.4)),
                  const SizedBox(height: 12),
                  const _SectionLabel(text: 'START TIME'),
                  const SizedBox(height: 8),
                  _DateTimePicker(
                    value: _customStartTime ?? DateTime.now().subtract(const Duration(hours: 1)),
                    onChanged: (dt) => setState(() => _customStartTime = dt),
                  ),
                ],

                // ── Custom stop time input ──
                if (_showStopTimeInput && _running) ...[
                  const SizedBox(height: 12),
                  Divider(height: 1, color: _borderColor.withValues(alpha: 0.4)),
                  const SizedBox(height: 12),
                  const _SectionLabel(text: 'STOP TIME'),
                  const SizedBox(height: 8),
                  _DateTimePicker(
                    value: _customStopTime ?? DateTime.now(),
                    onChanged: (dt) => setState(() => _customStopTime = dt),
                  ),
                ],
              ],
            ),
          ),

          // ── RUNNING badge ──
          if (_running)
            Positioned(
              top: 16, right: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: _accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: _accent.withValues(alpha: 0.2)),
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
                          color: _accent.withValues(alpha: 0.4 + _pulseController.value * 0.6),
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'RUNNING',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: _accent,
                        letterSpacing: 1.2,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildProjectSelector() {
    final hasSelection = _selectedProjectId != null;
    final projColor = hasSelection
        ? Color.fromARGB(255, _selectedProjectColor[0], _selectedProjectColor[1], _selectedProjectColor[2])
        : null;

    return GestureDetector(
      onTap: _showProjectPicker,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
        decoration: BoxDecoration(
          color: _bgColor,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: _borderColor),
        ),
        child: Row(
          children: [
            Icon(Icons.search, size: 16, color: _mutedFg.withValues(alpha: 0.4)),
            const SizedBox(width: 10),
            if (hasSelection) ...[
              Container(width: 8, height: 8, decoration: BoxDecoration(shape: BoxShape.circle, color: projColor)),
              const SizedBox(width: 8),
            ],
            Expanded(
              child: Text(
                hasSelection ? (_selectedProjectName ?? '') : 'Search projects...',
                style: TextStyle(
                  fontSize: 14,
                  color: hasSelection ? Colors.white : _mutedFg.withValues(alpha: 0.5),
                ),
              ),
            ),
            if (hasSelection)
              GestureDetector(
                onTap: () => setState(() {
                  _selectedProjectId = null;
                  _selectedProjectName = null;
                }),
                child: Icon(Icons.close, size: 16, color: _mutedFg.withValues(alpha: 0.5)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatsRow() {
    // Today's hours from elapsed (simple: current session only for now)
    final todayMinutes = _running ? _elapsed.inMinutes : 0;
    final todayStr = todayMinutes >= 60
        ? '${(todayMinutes / 60).toStringAsFixed(1)}h'
        : '${todayMinutes}m';

    return Row(
      children: [
        Expanded(
          child: _StatCard(label: 'Today', value: _running ? todayStr : '0.0h'),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _StatCard(label: 'This week', value: '—', accent: true),
        ),
      ],
    );
  }
}

// ─── Sub-components ─────────────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel({required this.text});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.w500,
        color: _labelColor,
        letterSpacing: 1.5,
      ),
    );
  }
}

class _TimerButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final Color textColor;
  final bool enabled;
  final VoidCallback onTap;

  const _TimerButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.textColor,
    required this.enabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 16, color: textColor),
            const SizedBox(width: 6),
            Text(label, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: textColor)),
          ],
        ),
      ),
    );
  }
}

class _CustomTimeToggle extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const _CustomTimeToggle({required this.label, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.calendar_today, size: 13,
                color: active ? _accent : _mutedFg.withValues(alpha: 0.5)),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                color: active ? _accent : _mutedFg.withValues(alpha: 0.5),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DateTimePicker extends StatelessWidget {
  final DateTime value;
  final ValueChanged<DateTime> onChanged;

  const _DateTimePicker({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        final date = await showDatePicker(
          context: context,
          initialDate: value,
          firstDate: DateTime.now().subtract(const Duration(days: 7)),
          lastDate: DateTime.now().add(const Duration(days: 1)),
        );
        if (date == null) return;
        if (!context.mounted) return;
        final time = await showTimePicker(
          context: context,
          initialTime: TimeOfDay.fromDateTime(value),
        );
        if (time == null) return;
        onChanged(DateTime(date.year, date.month, date.day, time.hour, time.minute));
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: _bgColor,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: _borderColor),
        ),
        child: Text(
          DateFormat('MMM d, yyyy  h:mm a').format(value),
          style: const TextStyle(fontSize: 14, color: Colors.white),
        ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final bool accent;

  const _StatCard({required this.label, required this.value, this.accent = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1714),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _borderColor.withValues(alpha: 0.5)),
      ),
      child: Column(
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 10, color: _labelColor, letterSpacing: 1.2, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: accent ? _accent : Colors.white,
              fontFeatures: [const FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Project Picker Bottom Sheet ────────────────────────────────────

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
          const SizedBox(height: 8),
          Container(width: 36, height: 4, decoration: BoxDecoration(color: _mutedFg.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(2))),
          const SizedBox(height: 16),
          const _SectionLabel(text: 'SELECT PROJECT'),
          const SizedBox(height: 12),

          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: TextField(
              autofocus: true,
              onChanged: (v) => setState(() => _query = v),
              style: const TextStyle(fontSize: 15, color: Colors.white),
              decoration: InputDecoration(
                hintText: 'Search projects...',
                hintStyle: TextStyle(color: _mutedFg.withValues(alpha: 0.5)),
                prefixIcon: Icon(Icons.search, size: 20, color: _mutedFg.withValues(alpha: 0.4)),
                filled: true,
                fillColor: _bgColor,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: _borderColor)),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: _borderColor)),
                focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: _accent.withValues(alpha: 0.4))),
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              ),
            ),
          ),
          const SizedBox(height: 8),

          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 320),
            child: filtered.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(20),
                    child: Text('No projects found', style: TextStyle(color: _mutedFg.withValues(alpha: 0.5))),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: filtered.length,
                    itemBuilder: (_, i) {
                      final p = filtered[i];
                      final rgb = (p['color_rgb'] as List?)?.cast<int>() ?? [150, 150, 150];
                      final color = Color.fromARGB(255, rgb[0], rgb[1], rgb[2]);
                      final name = p['name'] as String? ?? 'Unnamed';
                      final selected = p['id'] == widget.selectedId;

                      return GestureDetector(
                        onTap: () => widget.onSelected(p['id'], name, rgb),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                          decoration: BoxDecoration(
                            color: selected ? _accent.withValues(alpha: 0.08) : Colors.transparent,
                            border: Border(bottom: BorderSide(color: _borderColor.withValues(alpha: 0.4))),
                          ),
                          child: Row(
                            children: [
                              Container(width: 8, height: 8, decoration: BoxDecoration(shape: BoxShape.circle, color: color)),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Text(name, style: TextStyle(
                                  fontSize: 15,
                                  color: selected ? Colors.white : Colors.white.withValues(alpha: 0.8),
                                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                                )),
                              ),
                              if (selected) const Icon(Icons.check, size: 18, color: _accent),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
