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
      if (mounted) setState(() { _brief = brief; _review = review; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submitMood(int mood) async {
    setState(() => _todayMood = mood);
    try { await widget.client.postDailyNote(mood); } catch (_) {}
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
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
            children: [
              // ── Brief ──
              StaggeredEntrance(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(width: 3, height: 14, decoration: BoxDecoration(
                          color: BeatsColors.amber, borderRadius: BorderRadius.circular(2))),
                        const SizedBox(width: 10),
                        Text('MORNING BRIEF', style: BeatsType.label.copyWith(
                          color: BeatsColors.amber, letterSpacing: 2)),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (_brief != null)
                      Text(
                        _brief!['body'] ?? '',
                        style: GoogleFonts.dmSans(
                          fontSize: 15, height: 1.8,
                          color: BeatsColors.textPrimary.withValues(alpha: 0.85),
                          fontWeight: FontWeight.w400,
                        ),
                      )
                    else
                      Text(
                        'No brief today. The coach generates one each morning.',
                        style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary),
                      ),
                  ],
                ),
              ),

              Padding(
                padding: const EdgeInsets.symmetric(vertical: 32),
                child: Divider(height: 1, color: BeatsColors.border.withValues(alpha: 0.4)),
              ),

              // ── Review ──
              StaggeredEntrance(
                delay: const Duration(milliseconds: 80),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(width: 3, height: 14, decoration: BoxDecoration(
                          color: BeatsColors.textTertiary, borderRadius: BorderRadius.circular(2))),
                        const SizedBox(width: 10),
                        Text('EVENING REVIEW', style: BeatsType.label.copyWith(letterSpacing: 2)),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (_review != null && _review!['questions'] != null)
                      ..._buildQuestions()
                    else
                      Text(
                        'Review questions appear after your work day.',
                        style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary),
                      ),
                  ],
                ),
              ),

              Padding(
                padding: const EdgeInsets.symmetric(vertical: 32),
                child: Divider(height: 1, color: BeatsColors.border.withValues(alpha: 0.4)),
              ),

              // ── Mood ──
              StaggeredEntrance(
                delay: const Duration(milliseconds: 160),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('HOW WAS TODAY?', style: BeatsType.label.copyWith(letterSpacing: 2)),
                    const SizedBox(height: 20),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: List.generate(5, (i) {
                        final mood = i + 1;
                        final emojis = ['😫', '😕', '😐', '🙂', '😊'];
                        final labels = ['rough', 'meh', 'okay', 'good', 'great'];
                        final selected = _todayMood == mood;
                        return GestureDetector(
                          onTap: () => _submitMood(mood),
                          child: TweenAnimationBuilder<double>(
                            tween: Tween(begin: 1.0, end: selected ? 1.1 : 1.0),
                            duration: const Duration(milliseconds: 250),
                            curve: Curves.easeOutBack,
                            builder: (_, scale, child) =>
                                Transform.scale(scale: scale, child: child),
                            child: Column(
                              children: [
                                Container(
                                  width: 48, height: 48,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: selected
                                        ? BeatsColors.amber.withValues(alpha: 0.12)
                                        : Colors.transparent,
                                    border: Border.all(
                                      color: selected ? BeatsColors.amber : BeatsColors.border,
                                      width: selected ? 2 : 1,
                                    ),
                                  ),
                                  child: Center(
                                    child: Text(emojis[i],
                                        style: const TextStyle(fontSize: 22)),
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(labels[i],
                                  style: BeatsType.label.copyWith(
                                    fontSize: 8,
                                    color: selected
                                        ? BeatsColors.amber
                                        : BeatsColors.textTertiary,
                                  )),
                              ],
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

  List<Widget> _buildQuestions() {
    final questions = _review!['questions'] as List? ?? [];
    return questions.asMap().entries.map<Widget>((entry) {
      final i = entry.key;
      final q = entry.value;
      return Padding(
        padding: const EdgeInsets.only(bottom: 20),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${i + 1}',
              style: GoogleFonts.dmSerifDisplay(
                fontSize: 28, color: BeatsColors.amber.withValues(alpha: 0.3))),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 6),
                  Text(q['question'] ?? '',
                    style: BeatsType.bodyMedium.copyWith(
                      fontWeight: FontWeight.w500, height: 1.5)),
                  if (q['answer'] != null) ...[
                    const SizedBox(height: 8),
                    Text(q['answer'],
                      style: BeatsType.bodySmall.copyWith(
                        color: BeatsColors.textTertiary, height: 1.5)),
                  ],
                ],
              ),
            ),
          ],
        ),
      );
    }).toList();
  }
}
