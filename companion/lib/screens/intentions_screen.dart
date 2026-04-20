import 'package:flutter/material.dart';
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
      if (mounted) {
        setState(() { _intentions = intentions; _projects = projects; _loading = false; });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
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
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _AddIntentionSheet(projects: _projects),
    );
    if (result == null) return;
    try {
      await widget.client.createIntention(result['project_id'], result['planned_minutes']);
      await _refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    }
  }

  String _projectName(String projectId) {
    final p = _projects.where((p) => p['id'] == projectId).firstOrNull;
    return p?['name'] ?? projectId;
  }

  Color _projectColor(String projectId) {
    final p = _projects.where((p) => p['id'] == projectId).firstOrNull;
    final hex = p?['color'] as String?;
    if (hex == null || hex.length < 7) return BeatsColors.textTertiary;
    final h = hex.replaceFirst('#', '');
    return Color.fromARGB(255,
        int.parse(h.substring(0, 2), radix: 16),
        int.parse(h.substring(2, 4), radix: 16),
        int.parse(h.substring(4, 6), radix: 16));
  }

  String _formatMinutes(int m) => m >= 60 ? '${m ~/ 60}h${m % 60 > 0 ? ' ${m % 60}m' : ''}' : '${m}m';

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    final completed = _intentions.where((i) => i['completed'] == true).length;
    final total = _intentions.length;

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          color: BeatsColors.amber,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 80),
            children: [
              // Header with progress
              StaggeredEntrance(
                child: Row(
                  children: [
                    Expanded(
                      child: Text("Today's plan",
                          style: BeatsType.displayMedium.copyWith(fontSize: 24)),
                    ),
                    if (total > 0)
                      _ProgressRing(completed: completed, total: total),
                  ],
                ),
              ),
              const SizedBox(height: 20),

              if (_intentions.isEmpty)
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 60),
                  child: Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: BeatsColors.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: BeatsColors.border),
                    ),
                    child: Column(
                      children: [
                        Icon(Icons.checklist, size: 32,
                            color: BeatsColors.textTertiary.withValues(alpha: 0.3)),
                        const SizedBox(height: 12),
                        Text('No intentions set for today',
                            style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary)),
                        const SizedBox(height: 4),
                        Text('Tap + to plan your day',
                            style: BeatsType.bodySmall.copyWith(
                                color: BeatsColors.textTertiary.withValues(alpha: 0.6))),
                      ],
                    ),
                  ),
                ),

              ..._intentions.asMap().entries.map((entry) {
                final i = entry.key;
                final intention = entry.value;
                final done = intention['completed'] == true;
                final minutes = intention['planned_minutes'] ?? 60;
                final name = _projectName(intention['project_id'] ?? '');
                final color = _projectColor(intention['project_id'] ?? '');

                return StaggeredEntrance(
                  delay: Duration(milliseconds: 60 + i * 50),
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Container(
                      decoration: BoxDecoration(
                        color: BeatsColors.surface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: BeatsColors.border),
                      ),
                      child: Row(
                        children: [
                          // Project color bar
                          Container(
                            width: 3,
                            height: 56,
                            decoration: BoxDecoration(
                              color: done ? color.withValues(alpha: 0.3) : color,
                              borderRadius: const BorderRadius.horizontal(left: Radius.circular(12)),
                            ),
                          ),
                          // Checkbox
                          Checkbox(
                            value: done,
                            onChanged: (v) => _toggle(intention['id'], v ?? false),
                            activeColor: BeatsColors.amber,
                            side: BorderSide(color: BeatsColors.border),
                          ),
                          // Content
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    name,
                                    style: BeatsType.bodyMedium.copyWith(
                                      decoration: done ? TextDecoration.lineThrough : null,
                                      color: done
                                          ? BeatsColors.textTertiary
                                          : BeatsColors.textPrimary,
                                    ),
                                  ),
                                  Text(
                                    '${_formatMinutes(minutes)} planned',
                                    style: BeatsType.bodySmall.copyWith(
                                        color: BeatsColors.textTertiary),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          if (done)
                            Padding(
                              padding: const EdgeInsets.only(right: 12),
                              child: Icon(Icons.check_circle,
                                  size: 18, color: BeatsColors.green),
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
      floatingActionButton: FloatingActionButton(
        onPressed: _addIntention,
        backgroundColor: BeatsColors.amber,
        foregroundColor: const Color(0xFF1A1408),
        child: const Icon(Icons.add),
      ),
    );
  }
}

// Circular progress ring
class _ProgressRing extends StatelessWidget {
  final int completed;
  final int total;
  const _ProgressRing({required this.completed, required this.total});

  @override
  Widget build(BuildContext context) {
    final progress = total > 0 ? completed / total : 0.0;
    return SizedBox(
      width: 40, height: 40,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CircularProgressIndicator(
            value: progress,
            strokeWidth: 3,
            backgroundColor: BeatsColors.border,
            color: BeatsColors.amber,
          ),
          Text(
            '$completed/$total',
            style: BeatsType.label.copyWith(fontSize: 9, color: BeatsColors.textSecondary),
          ),
        ],
      ),
    );
  }
}

// Add intention bottom sheet
class _AddIntentionSheet extends StatefulWidget {
  final List<Map<String, dynamic>> projects;
  const _AddIntentionSheet({required this.projects});

  @override
  State<_AddIntentionSheet> createState() => _AddIntentionSheetState();
}

class _AddIntentionSheetState extends State<_AddIntentionSheet> {
  String? _selectedProjectId;
  int _minutes = 60;
  final _durations = [15, 30, 45, 60, 90, 120];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36, height: 4,
              decoration: BoxDecoration(
                color: BeatsColors.textTertiary.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text('ADD INTENTION', style: BeatsType.label.copyWith(color: BeatsColors.amber)),
          const SizedBox(height: 16),

          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: widget.projects.map((p) {
              final selected = _selectedProjectId == p['id'];
              return GestureDetector(
                onTap: () => setState(() => _selectedProjectId = p['id']),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: selected ? BeatsColors.amber.withValues(alpha: 0.15) : BeatsColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: selected ? BeatsColors.amber : BeatsColors.border,
                    ),
                  ),
                  child: Text(
                    p['name'] ?? 'Unnamed',
                    style: BeatsType.bodySmall.copyWith(
                      color: selected ? BeatsColors.amber : BeatsColors.textSecondary,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 20),

          Wrap(
            spacing: 8,
            children: _durations.map((d) {
              final selected = _minutes == d;
              return GestureDetector(
                onTap: () => setState(() => _minutes = d),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: selected ? BeatsColors.amber : BeatsColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: selected ? BeatsColors.amber : BeatsColors.border,
                    ),
                  ),
                  child: Text(
                    d >= 60 ? '${d ~/ 60}h${d % 60 > 0 ? ' ${d % 60}m' : ''}' : '${d}m',
                    style: BeatsType.bodySmall.copyWith(
                      color: selected ? const Color(0xFF1A1408) : BeatsColors.textSecondary,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 24),

          GestureDetector(
            onTap: _selectedProjectId != null
                ? () => Navigator.pop(context, {
                      'project_id': _selectedProjectId,
                      'planned_minutes': _minutes,
                    })
                : null,
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(
                color: _selectedProjectId != null ? BeatsColors.amber : BeatsColors.textTertiary.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Text(
                  'Add',
                  style: BeatsType.button.copyWith(
                    color: _selectedProjectId != null ? const Color(0xFF1A1408) : BeatsColors.textTertiary,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
