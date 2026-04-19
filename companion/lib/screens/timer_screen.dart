import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_client.dart';

// Beats theme colors (matching web UI)
const _bgColor = Color(0xFF1C1710);
const _cardColor = Color(0xFF1F1B15);
const _borderColor = Color(0xFF2E2A23);
const _accent = Color(0xFFD4952A);
const _destructive = Color(0xFFBF4040);
const _mutedFg = Color(0xFF8A7E6E);

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

  Future<void> _start() async {
    if (_selectedProjectId == null) return;
    setState(() {
      _running = true;
      _startTime = DateTime.now().toUtc();
      _elapsed = Duration.zero;
      _error = null;
    });
    _startTicker();
    try { await widget.client.startTimer(_selectedProjectId!); }
    catch (e) { setState(() => _error = '$e'); await _refresh(); }
  }

  Future<void> _stop() async {
    _stopTicker();
    final was = _running;
    setState(() { _running = false; _error = null; });
    try {
      await widget.client.stopTimer();
      setState(() { _startTime = null; _elapsed = Duration.zero; });
    } catch (e) { setState(() => _error = '$e'); if (was) await _refresh(); }
  }

  void _showProjectPicker() {
    showModalBottomSheet(
      context: context,
      backgroundColor: _cardColor,
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
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
            children: [
              // Timer card
              AnimatedContainer(
                duration: const Duration(milliseconds: 400),
                curve: Curves.easeOut,
                decoration: BoxDecoration(
                  color: _running ? const Color(0xFF231E14) : _cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _running ? _accent.withValues(alpha: 0.3) : _borderColor,
                  ),
                  boxShadow: _running
                      ? [BoxShadow(color: _accent.withValues(alpha: 0.12), blurRadius: 24, spreadRadius: -4)]
                      : [],
                ),
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    // Timer digits
                    Text(
                      _formatDigits(_elapsed),
                      style: TextStyle(
                        fontFamily: 'JetBrains Mono',
                        fontFamilyFallback: const ['monospace', 'Courier'],
                        fontSize: 44,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 2,
                        color: _running ? _accent : _mutedFg.withValues(alpha: 0.5),
                        fontFeatures: [const FontFeature.tabularFigures()],
                      ),
                    ),
                    const SizedBox(height: 8),

                    // Active project (running)
                    if (_running) ...[
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          // Pulsing amber dot
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
                          const SizedBox(width: 8),
                          // Project color dot
                          Container(
                            width: 8, height: 8,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: Color.fromARGB(255, _selectedProjectColor[0], _selectedProjectColor[1], _selectedProjectColor[2]),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            _selectedProjectName ?? '',
                            style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w500,
                              color: Colors.white,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 20),
                    ],

                    // Project selector (idle)
                    if (!_running) ...[
                      const SizedBox(height: 8),
                      GestureDetector(
                        onTap: _showProjectPicker,
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                          decoration: BoxDecoration(
                            color: _bgColor,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: _borderColor),
                          ),
                          child: Row(
                            children: [
                              if (_selectedProjectId != null) ...[
                                Container(
                                  width: 8, height: 8,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: Color.fromARGB(255, _selectedProjectColor[0], _selectedProjectColor[1], _selectedProjectColor[2]),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    _selectedProjectName ?? '',
                                    style: const TextStyle(fontSize: 14, color: Colors.white),
                                  ),
                                ),
                              ] else
                                Expanded(
                                  child: Text(
                                    'Select project...',
                                    style: TextStyle(fontSize: 14, color: _mutedFg.withValues(alpha: 0.6)),
                                  ),
                                ),
                              Icon(Icons.unfold_more, size: 18, color: _mutedFg.withValues(alpha: 0.4)),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // Action button
                    SizedBox(
                      width: double.infinity,
                      child: _running
                          ? _ActionButton(
                              label: 'Stop',
                              icon: Icons.stop_rounded,
                              color: _destructive,
                              onTap: _stop,
                            )
                          : _ActionButton(
                              label: 'Start',
                              icon: Icons.play_arrow_rounded,
                              color: _selectedProjectId != null ? _accent : _mutedFg.withValues(alpha: 0.3),
                              textColor: _selectedProjectId != null ? const Color(0xFF1A1408) : _mutedFg,
                              onTap: _selectedProjectId != null ? _start : null,
                            ),
                    ),
                  ],
                ),
              ),

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
}

// ─── Action Button ──────────────────────────────────────────────────

class _ActionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final Color? textColor;
  final VoidCallback? onTap;

  const _ActionButton({
    required this.label,
    required this.icon,
    required this.color,
    this.textColor,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final fg = textColor ?? Colors.white;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 18, color: fg),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: fg,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Project Picker Bottom Sheet ────────────────────────────────────

class _ProjectPickerSheet extends StatefulWidget {
  final List<Map<String, dynamic>> projects;
  final String? selectedId;
  final void Function(String id, String name, List<int> color) onSelected;

  const _ProjectPickerSheet({
    required this.projects,
    this.selectedId,
    required this.onSelected,
  });

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
          // Handle
          const SizedBox(height: 8),
          Container(
            width: 36, height: 4,
            decoration: BoxDecoration(
              color: _mutedFg.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 16),

          // Search
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
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: _borderColor),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: _borderColor),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: _accent.withValues(alpha: 0.4)),
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              ),
            ),
          ),
          const SizedBox(height: 8),

          // List
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 320),
            child: ListView.builder(
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
                      border: Border(bottom: BorderSide(color: _borderColor.withValues(alpha: 0.5))),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 8, height: 8,
                          decoration: BoxDecoration(shape: BoxShape.circle, color: color),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            name,
                            style: TextStyle(
                              fontSize: 15,
                              color: selected ? Colors.white : Colors.white.withValues(alpha: 0.8),
                              fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                            ),
                          ),
                        ),
                        if (selected)
                          Icon(Icons.check, size: 18, color: _accent),
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
