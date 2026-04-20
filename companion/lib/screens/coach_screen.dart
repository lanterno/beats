import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';

class CoachScreen extends StatefulWidget {
  final ApiClient client;
  const CoachScreen({super.key, required this.client});

  @override
  State<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends State<CoachScreen> {
  bool _loading = true;
  Map<String, dynamic>? _brief;
  Map<String, dynamic>? _review;
  int? _todayMood;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final brief = await widget.client.getTodayBrief();
      final review = await widget.client.getTodayReview();
      if (mounted) {
        setState(() {
          _brief = brief;
          _review = review;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submitMood(int mood) async {
    setState(() => _todayMood = mood);
    try {
      await widget.client.postDailyNote(mood);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Mood logged: ${'😫😕😐🙂😊'[mood - 1]}')),
        );
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: BeatsColors.amber));
    }

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          // Morning brief
          _SectionTitle(icon: Icons.wb_sunny, title: 'Morning Brief'),
          const SizedBox(height: 8),
          if (_brief != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  _brief!['body'] ?? 'No brief available.',
                  style: theme.textTheme.bodyMedium?.copyWith(height: 1.6),
                ),
              ),
            )
          else
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'No brief generated today. The coach generates briefs automatically each morning.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ),
            ),
          const SizedBox(height: 24),

          // Evening review
          _SectionTitle(icon: Icons.nightlight_round, title: 'Evening Review'),
          const SizedBox(height: 8),
          if (_review != null && _review!['questions'] != null)
            ..._buildReviewQuestions(theme)
          else
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'No review questions yet. They appear after your work day.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ),
            ),
          const SizedBox(height: 24),

          // Mood picker
          _SectionTitle(icon: Icons.emoji_emotions, title: 'How was your day?'),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: List.generate(5, (i) {
              final mood = i + 1;
              final emojis = ['😫', '😕', '😐', '🙂', '😊'];
              final selected = _todayMood == mood;
              return GestureDetector(
                onTap: () => _submitMood(mood),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: selected
                        ? theme.colorScheme.primary.withValues(alpha: 0.2)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(12),
                    border: selected
                        ? Border.all(color: theme.colorScheme.primary, width: 2)
                        : null,
                  ),
                  child: Text(emojis[i], style: const TextStyle(fontSize: 32)),
                ),
              );
            }),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildReviewQuestions(ThemeData theme) {
    final questions = _review!['questions'] as List? ?? [];
    return questions.map<Widget>((q) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  q['question'] ?? '',
                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500),
                ),
                if (q['answer'] != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    q['answer'],
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }).toList();
  }
}

class _SectionTitle extends StatelessWidget {
  final IconData icon;
  final String title;
  const _SectionTitle({required this.icon, required this.title});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Icon(icon, size: 18, color: theme.colorScheme.primary),
        const SizedBox(width: 8),
        Text(title, style: theme.textTheme.titleSmall),
      ],
    );
  }
}
