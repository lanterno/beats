import 'dart:async';
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
  String _todayNote = '';
  bool _savingNote = false;
  Timer? _noteSaveTimer;
  final TextEditingController _noteController = TextEditingController();

  /// Last 7 days of moods, keyed by ISO date — used for the sparkline.
  Map<String, int> _moodHistory = {};

  // Per-question editing state, keyed by question index.
  final Map<int, TextEditingController> _answerControllers = {};
  final Set<int> _expandedQuestions = {};
  final Map<int, Timer> _saveTimers = {};
  final Set<int> _savingQuestions = {};

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _noteSaveTimer?.cancel();
    _noteController.dispose();
    for (final t in _saveTimers.values) {
      t.cancel();
    }
    for (final c in _answerControllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  String _todayKey() {
    final now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
  }

  Future<void> _refresh() async {
    try {
      final brief = await widget.client.getTodayBrief();
      final review = await widget.client.getTodayReview();

      // Pull the last 7 days of daily notes for the sparkline + today's row.
      final today = DateTime.now();
      String fmt(DateTime d) =>
          '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
      final start = today.subtract(const Duration(days: 6));
      final notes = await widget.client.getDailyNotesRange(fmt(start), fmt(today));

      final moods = <String, int>{};
      String? todayNote;
      int? todayMood;
      for (final n in notes) {
        final d = n['date'] as String?;
        if (d == null) continue;
        final m = (n['mood'] as num?)?.toInt();
        if (m != null) moods[d] = m;
        if (d == _todayKey()) {
          todayMood = m;
          final note = n['note'] as String?;
          if (note != null) todayNote = note;
        }
      }

      if (mounted) {
        setState(() {
          _brief = brief;
          _review = review;
          _moodHistory = moods;
          _todayMood = todayMood;
          _todayNote = todayNote ?? '';
          _loading = false;
        });
        if (_noteController.text != _todayNote) {
          _noteController.text = _todayNote;
        }
        _syncAnswerControllers();
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Keep TextEditingControllers in sync with whatever answers came back from the API.
  /// We don't blow away controllers the user is editing — only seed empty ones.
  void _syncAnswerControllers() {
    final answers = (_review?['answers'] as List?) ?? const [];
    for (var i = 0; i < answers.length; i++) {
      final existing = answers[i];
      final text = existing is String ? existing : '';
      final controller = _answerControllers.putIfAbsent(
        i,
        () => TextEditingController(text: text),
      );
      if (controller.text.isEmpty && text.isNotEmpty) {
        controller.text = text;
      }
    }
  }

  Future<void> _submitMood(int mood) async {
    setState(() {
      _todayMood = mood;
      _moodHistory[_todayKey()] = mood;
    });
    try {
      await widget.client.upsertDailyNote(mood: mood, note: _noteController.text);
    } catch (_) {}
  }

  void _onNoteChanged(String value) {
    _noteSaveTimer?.cancel();
    _noteSaveTimer = Timer(const Duration(milliseconds: 800), () {
      _saveNote(value);
    });
  }

  Future<void> _saveNote(String value) async {
    setState(() => _savingNote = true);
    try {
      await widget.client.upsertDailyNote(mood: _todayMood, note: value);
      if (!mounted) return;
      setState(() {
        _todayNote = value;
        _savingNote = false;
      });
    } catch (_) {
      if (mounted) setState(() => _savingNote = false);
    }
  }

  void _toggleQuestion(int index) {
    setState(() {
      if (_expandedQuestions.contains(index)) {
        _expandedQuestions.remove(index);
      } else {
        _expandedQuestions.add(index);
      }
    });
  }

  void _onAnswerChanged(int index, String value) {
    _saveTimers[index]?.cancel();
    _saveTimers[index] = Timer(const Duration(milliseconds: 800), () {
      _saveAnswer(index, value);
    });
  }

  Future<void> _saveAnswer(int index, String value) async {
    final date = _review?['date'] as String?;
    if (date == null) return;
    final trimmed = value.trim();
    if (trimmed.isEmpty) return;

    setState(() => _savingQuestions.add(index));
    try {
      await widget.client.answerReview(date, index, trimmed);
      if (!mounted) return;
      // Reflect the saved answer in our local copy of the review doc so the
      // progress indicator picks it up without an extra round-trip.
      final answers = List<dynamic>.from((_review?['answers'] as List?) ?? const []);
      while (answers.length <= index) {
        answers.add(null);
      }
      answers[index] = trimmed;
      setState(() {
        _review = {...?_review, 'answers': answers};
        _savingQuestions.remove(index);
      });
    } catch (_) {
      if (mounted) setState(() => _savingQuestions.remove(index));
    }
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
                        const Spacer(),
                        if (_review != null && _review!['questions'] != null)
                          Text(_progressLabel(),
                            style: BeatsType.label.copyWith(
                              fontSize: 9,
                              color: BeatsColors.textTertiary,
                              letterSpacing: 1.5,
                            )),
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
                    Row(
                      children: [
                        Text('HOW WAS TODAY?', style: BeatsType.label.copyWith(letterSpacing: 2)),
                        const Spacer(),
                        if (_moodHistory.length > 1) _buildMoodSparkline(),
                      ],
                    ),
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
                    const SizedBox(height: 24),
                    Row(
                      children: [
                        Text('WHAT WENT WELL?', style: BeatsType.label.copyWith(letterSpacing: 2)),
                        const Spacer(),
                        if (_savingNote)
                          Text('SAVING…', style: BeatsType.label.copyWith(
                            fontSize: 9, color: BeatsColors.textTertiary, letterSpacing: 1.5)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _noteController,
                      onChanged: _onNoteChanged,
                      onEditingComplete: () => _saveNote(_noteController.text),
                      maxLines: null,
                      minLines: 2,
                      style: BeatsType.bodySmall.copyWith(
                        color: BeatsColors.textPrimary, height: 1.5),
                      cursorColor: BeatsColors.amber,
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 0, vertical: 8),
                        hintText: 'A line or two — optional',
                        hintStyle: BeatsType.bodySmall.copyWith(
                          color: BeatsColors.textTertiary.withValues(alpha: 0.5)),
                        enabledBorder: UnderlineInputBorder(
                          borderSide: BorderSide(
                            color: BeatsColors.border.withValues(alpha: 0.6))),
                        focusedBorder: const UnderlineInputBorder(
                          borderSide: BorderSide(color: BeatsColors.amber)),
                      ),
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

  /// Render the last 7 days of moods as small dots, color-coded.
  /// Days without an entry render as a faint placeholder so the row keeps
  /// the same width regardless of how much data is present.
  Widget _buildMoodSparkline() {
    final today = DateTime.now();
    final days = List.generate(7, (i) {
      final d = today.subtract(Duration(days: 6 - i));
      final key =
          '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
      return _moodHistory[key];
    });

    Color colorFor(int? mood) {
      if (mood == null) return BeatsColors.border.withValues(alpha: 0.5);
      // 1 = rough → red, 5 = great → green, 3 in the middle → amber.
      if (mood <= 2) return BeatsColors.red;
      if (mood >= 4) return BeatsColors.green;
      return BeatsColors.amber;
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < days.length; i++) ...[
          if (i > 0) const SizedBox(width: 4),
          Container(
            width: days[i] == null ? 4 : 6,
            height: days[i] == null ? 4 : 6,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: colorFor(days[i]),
            ),
          ),
        ],
      ],
    );
  }

  String _progressLabel() {
    final questions = (_review?['questions'] as List?) ?? const [];
    final total = questions.length;
    final answers = (_review?['answers'] as List?) ?? const [];
    var answered = 0;
    for (final a in answers) {
      if (a is String && a.trim().isNotEmpty) answered++;
    }
    return '$answered OF $total ANSWERED';
  }

  List<Widget> _buildQuestions() {
    final questions = _review!['questions'] as List? ?? [];
    final answers = (_review?['answers'] as List?) ?? const [];
    return questions.asMap().entries.map<Widget>((entry) {
      final i = entry.key;
      final q = entry.value;
      final savedAnswer = i < answers.length && answers[i] is String
          ? answers[i] as String
          : '';
      final hasAnswer = savedAnswer.trim().isNotEmpty;
      final isExpanded = _expandedQuestions.contains(i) || !hasAnswer;
      final controller = _answerControllers.putIfAbsent(
        i,
        () => TextEditingController(text: savedAnswer),
      );
      final isSaving = _savingQuestions.contains(i);

      return Padding(
        padding: const EdgeInsets.only(bottom: 20),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: hasAnswer ? () => _toggleQuestion(i) : null,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${i + 1}',
                style: GoogleFonts.dmSerifDisplay(
                  fontSize: 28,
                  color: hasAnswer
                      ? BeatsColors.amber
                      : BeatsColors.amber.withValues(alpha: 0.3),
                )),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 6),
                    Text(q['question'] ?? '',
                      style: BeatsType.bodyMedium.copyWith(
                        fontWeight: FontWeight.w500, height: 1.5)),
                    if (isExpanded) ...[
                      const SizedBox(height: 12),
                      TextField(
                        controller: controller,
                        onChanged: (v) => _onAnswerChanged(i, v),
                        onEditingComplete: () => _saveAnswer(i, controller.text),
                        maxLines: null,
                        minLines: 2,
                        style: BeatsType.bodySmall.copyWith(
                          color: BeatsColors.textPrimary, height: 1.5),
                        cursorColor: BeatsColors.amber,
                        decoration: InputDecoration(
                          isDense: true,
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 0, vertical: 8),
                          hintText: 'Write a few words…',
                          hintStyle: BeatsType.bodySmall.copyWith(
                            color: BeatsColors.textTertiary.withValues(alpha: 0.5),
                          ),
                          enabledBorder: UnderlineInputBorder(
                            borderSide: BorderSide(
                              color: BeatsColors.border.withValues(alpha: 0.6),
                            ),
                          ),
                          focusedBorder: const UnderlineInputBorder(
                            borderSide: BorderSide(color: BeatsColors.amber),
                          ),
                        ),
                      ),
                      if (isSaving)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text('SAVING…',
                            style: BeatsType.label.copyWith(
                              fontSize: 9,
                              color: BeatsColors.textTertiary,
                              letterSpacing: 1.5,
                            )),
                        ),
                    ] else ...[
                      const SizedBox(height: 8),
                      Text(savedAnswer,
                        style: BeatsType.bodySmall.copyWith(
                          color: BeatsColors.textTertiary, height: 1.5)),
                      const SizedBox(height: 4),
                      Text('TAP TO EDIT',
                        style: BeatsType.label.copyWith(
                          fontSize: 8,
                          color: BeatsColors.textTertiary.withValues(alpha: 0.6),
                          letterSpacing: 1.5,
                        )),
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
