import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

class IntentionsScreen extends StatefulWidget {
  final ApiClient client;
  const IntentionsScreen({super.key, required this.client});

  @override
  State<IntentionsScreen> createState() => _IntentionsScreenState();
}

class _IntentionsScreenState extends State<IntentionsScreen> {
  bool _loading = true;
  List<Map<String, dynamic>> _intentions = [];
  List<Map<String, dynamic>> _projects = [];

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final intentions = await widget.client.getIntentions();
      final projects = await widget.client.getProjects();
      if (mounted) setState(() { _intentions = intentions; _projects = projects; _loading = false; });
    } catch (_) { if (mounted) setState(() => _loading = false); }
  }

  Future<void> _toggle(String id, bool completed) async {
    setState(() {
      final idx = _intentions.indexWhere((i) => i['id'] == id);
      if (idx >= 0) _intentions[idx]['completed'] = completed;
    });
    try { await widget.client.toggleIntention(id, completed); }
    catch (_) { await _refresh(); }
  }

  Future<void> _addIntention() async {
    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      backgroundColor: BeatsColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => _AddSheet(projects: _projects),
    );
    if (result == null) return;
    try {
      await widget.client.createIntention(result['project_id'], result['planned_minutes']);
      await _refresh();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed: $e')));
    }
  }

  String _projectName(String id) =>
      (_projects.where((p) => p['id'] == id).firstOrNull)?['name'] ?? id;

  Color _projectColor(String id) {
    final hex = (_projects.where((p) => p['id'] == id).firstOrNull)?['color'] as String?;
    if (hex == null || hex.length < 7) return BeatsColors.textTertiary;
    final h = hex.replaceFirst('#', '');
    return Color.fromARGB(255,
        int.parse(h.substring(0, 2), radix: 16),
        int.parse(h.substring(2, 4), radix: 16),
        int.parse(h.substring(4, 6), radix: 16));
  }

  String _fmt(int m) => m >= 60 ? '${m ~/ 60}h${m % 60 > 0 ? ' ${m % 60}m' : ''}' : '${m}m';

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    final done = _intentions.where((i) => i['completed'] == true).length;
    final total = _intentions.length;

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          color: BeatsColors.amber,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
            children: [
              // ── Header ──
              StaggeredEntrance(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('Plan',
                      style: GoogleFonts.dmSerifDisplay(
                        fontSize: 32, color: BeatsColors.textPrimary)),
                    const Spacer(),
                    if (total > 0) ...[
                      Text('$done', style: GoogleFonts.jetBrainsMono(
                        fontSize: 24, fontWeight: FontWeight.w300, color: BeatsColors.amber)),
                      Text(' / $total', style: GoogleFonts.jetBrainsMono(
                        fontSize: 24, fontWeight: FontWeight.w300, color: BeatsColors.textTertiary)),
                    ],
                  ],
                ),
              ),

              // ── Progress bar ──
              if (total > 0) ...[
                const SizedBox(height: 12),
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 40),
                  child: TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: done / total),
                    duration: const Duration(milliseconds: 600),
                    curve: Curves.easeOutCubic,
                    builder: (_, val, _) => Container(
                      height: 3,
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
                            color: BeatsColors.amber,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 28),

              // ── Intentions ──
              if (_intentions.isEmpty)
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 80),
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 32),
                      child: Column(
                        children: [
                          Icon(Icons.wb_twilight, size: 32,
                            color: BeatsColors.textTertiary.withValues(alpha: 0.2)),
                          const SizedBox(height: 16),
                          Text('No intentions today',
                            style: BeatsType.bodyMedium.copyWith(
                              color: BeatsColors.textTertiary)),
                          const SizedBox(height: 4),
                          Text('Tap + to plan your day',
                            style: BeatsType.bodySmall.copyWith(
                              color: BeatsColors.textTertiary.withValues(alpha: 0.5))),
                        ],
                      ),
                    ),
                  ),
                ),

              ..._intentions.asMap().entries.map((entry) {
                final i = entry.key;
                final item = entry.value;
                final isDone = item['completed'] == true;
                final minutes = item['planned_minutes'] ?? 60;
                final name = _projectName(item['project_id'] ?? '');
                final color = _projectColor(item['project_id'] ?? '');

                return StaggeredEntrance(
                  delay: Duration(milliseconds: 80 + i * 60),
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: GestureDetector(
                      onTap: () => _toggle(item['id'], !isDone),
                      child: Row(
                        children: [
                          // Color bar
                          Container(width: 3, height: 44,
                            decoration: BoxDecoration(
                              color: isDone ? color.withValues(alpha: 0.2) : color,
                              borderRadius: BorderRadius.circular(2))),
                          const SizedBox(width: 16),
                          // Check circle
                          Container(
                            width: 22, height: 22,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: isDone ? BeatsColors.amber.withValues(alpha: 0.15) : Colors.transparent,
                              border: Border.all(
                                color: isDone ? BeatsColors.amber : BeatsColors.border,
                                width: 1.5),
                            ),
                            child: isDone
                                ? const Icon(Icons.check, size: 14, color: BeatsColors.amber)
                                : null,
                          ),
                          const SizedBox(width: 14),
                          // Content
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(name, style: BeatsType.bodyMedium.copyWith(
                                  color: isDone ? BeatsColors.textTertiary : BeatsColors.textPrimary,
                                  decoration: isDone ? TextDecoration.lineThrough : null,
                                  decorationColor: BeatsColors.textTertiary,
                                )),
                                Text(_fmt(minutes), style: BeatsType.bodySmall.copyWith(
                                  fontSize: 11, color: BeatsColors.textTertiary)),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.small(
        onPressed: _addIntention,
        backgroundColor: BeatsColors.amber,
        foregroundColor: const Color(0xFF1A1408),
        elevation: 0,
        child: const Icon(Icons.add, size: 20),
      ),
    );
  }
}

class _AddSheet extends StatefulWidget {
  final List<Map<String, dynamic>> projects;
  const _AddSheet({required this.projects});
  @override
  State<_AddSheet> createState() => _AddSheetState();
}

class _AddSheetState extends State<_AddSheet> {
  String? _pid;
  int _min = 60;
  final _durs = [15, 30, 45, 60, 90, 120];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(child: Container(width: 40, height: 4, decoration: BoxDecoration(
            color: BeatsColors.textTertiary.withValues(alpha: 0.2),
            borderRadius: BorderRadius.circular(2)))),
          const SizedBox(height: 24),
          Text('ADD INTENTION', style: BeatsType.label.copyWith(
            color: BeatsColors.amber, letterSpacing: 2)),
          const SizedBox(height: 20),

          // Projects
          Wrap(spacing: 8, runSpacing: 8,
            children: widget.projects.map((p) {
              final sel = _pid == p['id'];
              return GestureDetector(
                onTap: () => setState(() => _pid = p['id']),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    color: sel ? BeatsColors.amber.withValues(alpha: 0.12) : Colors.transparent,
                    border: Border.all(color: sel ? BeatsColors.amber : BeatsColors.border),
                  ),
                  child: Text(p['name'] ?? '', style: BeatsType.bodySmall.copyWith(
                    color: sel ? BeatsColors.amber : BeatsColors.textSecondary,
                    fontWeight: sel ? FontWeight.w600 : FontWeight.w400)),
                ),
              );
            }).toList()),
          const SizedBox(height: 20),

          // Durations
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: _durs.map((d) {
              final sel = _min == d;
              return GestureDetector(
                onTap: () => setState(() => _min = d),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                    color: sel ? BeatsColors.amber : Colors.transparent,
                    border: Border.all(
                      color: sel ? BeatsColors.amber : BeatsColors.border),
                  ),
                  child: Text(
                    d >= 60 ? '${d ~/ 60}h' : '${d}m',
                    style: BeatsType.bodySmall.copyWith(
                      color: sel ? const Color(0xFF1A1408) : BeatsColors.textTertiary,
                      fontWeight: sel ? FontWeight.w600 : FontWeight.w400),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 24),

          GestureDetector(
            onTap: _pid != null
                ? () => Navigator.pop(context, {'project_id': _pid, 'planned_minutes': _min})
                : null,
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(
                color: _pid != null ? BeatsColors.amber : BeatsColors.border,
                borderRadius: BorderRadius.circular(12)),
              child: Center(child: Text('Add', style: BeatsType.button.copyWith(
                color: _pid != null ? const Color(0xFF1A1408) : BeatsColors.textTertiary))),
            ),
          ),
        ],
      ),
    );
  }
}
