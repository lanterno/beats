import 'package:flutter/material.dart';
import '../services/api_client.dart';

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
        setState(() {
          _intentions = intentions;
          _projects = projects;
          _loading = false;
        });
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
    try {
      await widget.client.toggleIntention(id, completed);
    } catch (_) {
      await _refresh();
    }
  }

  Future<void> _addIntention() async {
    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => _AddIntentionSheet(projects: _projects),
    );
    if (result == null) return;

    try {
      await widget.client.createIntention(
        result['project_id'],
        result['planned_minutes'],
      );
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          children: [
            Text("Today's intentions", style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w300)),
            const SizedBox(height: 16),

            if (_intentions.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(
                    'No intentions set for today.\nTap + to plan your day.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),

            ..._intentions.map((intention) {
              final completed = intention['completed'] == true;
              final minutes = intention['planned_minutes'] ?? 60;
              final name = _projectName(intention['project_id'] ?? '');

              return Card(
                child: ListTile(
                  leading: Checkbox(
                    value: completed,
                    onChanged: (v) => _toggle(intention['id'], v ?? false),
                    activeColor: theme.colorScheme.primary,
                  ),
                  title: Text(
                    name,
                    style: TextStyle(
                      decoration: completed ? TextDecoration.lineThrough : null,
                      color: completed
                          ? theme.colorScheme.onSurface.withValues(alpha: 0.4)
                          : null,
                    ),
                  ),
                  subtitle: Text('${_formatMinutes(minutes)} planned'),
                  trailing: completed
                      ? Icon(Icons.check_circle, color: theme.colorScheme.primary, size: 20)
                      : null,
                ),
              );
            }),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _addIntention,
        child: const Icon(Icons.add),
      ),
    );
  }

  String _formatMinutes(int minutes) {
    if (minutes >= 60) {
      final h = minutes ~/ 60;
      final m = minutes % 60;
      return m > 0 ? '${h}h ${m}m' : '${h}h';
    }
    return '${minutes}m';
  }
}

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
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Add intention', style: theme.textTheme.titleMedium),
          const SizedBox(height: 16),

          // Project picker
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: widget.projects.map((p) {
              final selected = _selectedProjectId == p['id'];
              return ChoiceChip(
                label: Text(p['name'] ?? 'Unnamed'),
                selected: selected,
                onSelected: (_) => setState(() => _selectedProjectId = p['id']),
              );
            }).toList(),
          ),
          const SizedBox(height: 16),

          // Duration picker
          Wrap(
            spacing: 8,
            children: _durations.map((d) {
              final selected = _minutes == d;
              return ChoiceChip(
                label: Text(d >= 60 ? '${d ~/ 60}h${d % 60 > 0 ? ' ${d % 60}m' : ''}' : '${d}m'),
                selected: selected,
                onSelected: (_) => setState(() => _minutes = d),
              );
            }).toList(),
          ),
          const SizedBox(height: 24),

          FilledButton(
            onPressed: _selectedProjectId != null
                ? () => Navigator.pop(context, {
                      'project_id': _selectedProjectId,
                      'planned_minutes': _minutes,
                    })
                : null,
            child: const Text('Add'),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
