import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

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
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

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
              // Morning Brief
              StaggeredEntrance(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.wb_sunny_outlined, size: 16, color: BeatsColors.amber),
                        const SizedBox(width: 8),
                        Text('MORNING BRIEF', style: BeatsType.label.copyWith(color: BeatsColors.amber)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Container(
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: BeatsColors.surface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: BeatsColors.border),
                      ),
                      child: Stack(
                        children: [
                          // Sunrise gradient overlay
                          Positioned(
                            top: 0, left: 0, right: 0,
                            child: Container(
                              height: 40,
                              decoration: BoxDecoration(
                                borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                                gradient: LinearGradient(
                                  begin: Alignment.topCenter,
                                  end: Alignment.bottomCenter,
                                  colors: [
                                    BeatsColors.amber.withValues(alpha: 0.06),
                                    Colors.transparent,
                                  ],
                                ),
                              ),
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.all(20),
                            child: _brief != null
                                ? Text(
                                    _brief!['body'] ?? 'No brief available.',
                                    style: GoogleFonts.dmSans(
                                      fontSize: 14,
                                      height: 1.7,
                                      color: BeatsColors.textPrimary,
                                    ),
                                  )
                                : Text(
                                    'No brief generated today.\nThe coach creates one each morning.',
                                    style: BeatsType.bodySmall.copyWith(
                                      color: BeatsColors.textTertiary,
                                    ),
                                  ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),

              // Evening Review
              StaggeredEntrance(
                delay: const Duration(milliseconds: 80),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.nightlight_outlined, size: 16, color: BeatsColors.textSecondary),
                        const SizedBox(width: 8),
                        Text('EVENING REVIEW', style: BeatsType.label),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (_review != null && _review!['questions'] != null)
                      ..._buildNumberedQuestions()
                    else
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: BeatsColors.surface,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: BeatsColors.border),
                        ),
                        child: Text(
                          'Review questions appear after your work day.',
                          style: BeatsType.bodySmall.copyWith(color: BeatsColors.textTertiary),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 28),

              // Mood Picker
              StaggeredEntrance(
                delay: const Duration(milliseconds: 160),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.emoji_emotions_outlined, size: 16, color: BeatsColors.textSecondary),
                        const SizedBox(width: 8),
                        Text('HOW WAS YOUR DAY?', style: BeatsType.label),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: List.generate(5, (i) {
                        final mood = i + 1;
                        final emojis = ['😫', '😕', '😐', '🙂', '😊'];
                        final selected = _todayMood == mood;
                        return GestureDetector(
                          onTap: () => _submitMood(mood),
                          child: TweenAnimationBuilder<double>(
                            tween: Tween(begin: 1.0, end: selected ? 1.15 : 1.0),
                            duration: const Duration(milliseconds: 300),
                            curve: Curves.easeOutBack,
                            builder: (_, scale, child) => Transform.scale(
                              scale: scale,
                              child: child,
                            ),
                            child: Container(
                              width: 52, height: 52,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: selected
                                    ? BeatsColors.amber.withValues(alpha: 0.15)
                                    : BeatsColors.surface,
                                border: Border.all(
                                  color: selected ? BeatsColors.amber : BeatsColors.border,
                                  width: selected ? 2 : 1,
                                ),
                              ),
                              child: Center(
                                child: Text(emojis[i], style: const TextStyle(fontSize: 24)),
                              ),
                            ),
                          ),
                        );
                      }),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildNumberedQuestions() {
    final questions = _review!['questions'] as List? ?? [];
    return questions.asMap().entries.map<Widget>((entry) {
      final i = entry.key;
      final q = entry.value;
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: BeatsColors.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: BeatsColors.border),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Large numbered circle
              Container(
                width: 28, height: 28,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: BeatsColors.amber.withValues(alpha: 0.1),
                ),
                child: Center(
                  child: Text(
                    '${i + 1}',
                    style: BeatsType.monoSmall.copyWith(
                        fontSize: 13, color: BeatsColors.amber),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      q['question'] ?? '',
                      style: BeatsType.bodyMedium.copyWith(fontWeight: FontWeight.w500),
                    ),
                    if (q['answer'] != null) ...[
                      const SizedBox(height: 8),
                      Text(q['answer'],
                          style: BeatsType.bodySmall.copyWith(color: BeatsColors.textTertiary)),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }).toList();
  }
}
