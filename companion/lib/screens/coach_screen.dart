import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_client.dart';
import '../services/coach_story.dart';
import '../services/local_timezone.dart';
import '../services/time_format.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'timer_actions.dart';

/// Coach: the morning brief as a letter, where each project's week stands,
/// and a chat with the coach beside them.
class CoachScreen extends StatefulWidget {
  final ApiClient client;
  final TimerController timer;
  final WeekController week;

  const CoachScreen({super.key, required this.client, required this.timer, required this.week});

  @override
  State<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends State<CoachScreen> {
  static const _conversationKey = 'lifepete_coach_conversation';

  Map<String, dynamic>? _brief;
  bool _briefLoaded = false;
  bool _writing = false;
  String? _memory;
  DateTime? _memoryUpdated;

  final _messages = <ChatMessage>[];
  ChatReply? _reply;
  String? _conversationId;
  bool _streaming = false;
  bool _chatForbidden = false;
  final _input = TextEditingController();
  final _inputFocus = FocusNode();
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _loadBrief();
    _restoreChat();
    _loadMemory();
  }

  Future<void> _loadMemory() async {
    try {
      final m = await widget.client.getCoachMemory();
      if (!mounted) return;
      setState(() {
        _memory = m['content'] as String?;
        _memoryUpdated = DateTime.tryParse(m['updated_at'] as String? ?? '')?.toLocal();
      });
    } catch (_) {
      // An older server refuses devices here; the chip simply doesn't show.
    }
  }

  /// Writes today's brief now, since nothing writes it on a schedule.
  Future<void> _writeBrief() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _writing = true);
    try {
      final brief = await widget.client.generateBrief(timezone: await localTimezone());
      if (!mounted) return;
      setState(() => _brief = brief);
    } catch (e) {
      final budget = e is ApiException && e.code == 'BUDGET_EXCEEDED';
      messenger.showSnackBar(SnackBar(
        content: Text(budget ? 'You\'ve reached this month\'s coach budget.' : 'Couldn\'t write the brief: $e'),
      ));
    } finally {
      if (mounted) setState(() => _writing = false);
    }
  }

  /// Rates the brief; choosing the rating it already has clears it.
  Future<void> _rate(String rating) async {
    final brief = _brief;
    final date = brief?['date'] as String?;
    if (brief == null || date == null) return;
    final next = brief['feedback'] == rating ? null : rating;
    setState(() => _brief = {...brief, 'feedback': next});
    try {
      final saved = await widget.client.setBriefFeedback(date, next);
      if (mounted) setState(() => _brief = saved);
    } catch (e) {
      if (!mounted) return;
      setState(() => _brief = brief);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Couldn\'t save that: $e')));
    }
  }

  Future<void> _showMemory() async {
    final p = context.sky;
    await showDialog<void>(
      context: context,
      builder: (ctx) => Dialog(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560, maxHeight: 560),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(28, 24, 28, 18),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text('What your coach remembers', style: SkyType.display(20)),
              if (_memoryUpdated != null) ...[
                const SizedBox(height: 4),
                Text('Updated ${DateFormat('d MMMM').format(_memoryUpdated!)}',
                    style: SkyType.body(13).copyWith(color: p.inkMuted)),
              ],
              const SizedBox(height: 14),
              Flexible(
                child: SingleChildScrollView(
                  child: SelectableText(_memory ?? '', style: SkyType.body(14, height: 1.7)),
                ),
              ),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: Text('Rewrite or clear it from the coach on the web.',
                      style: SkyType.body(12).copyWith(color: p.inkMuted)),
                ),
                SkyButton(label: 'Close', onPressed: () => Navigator.of(ctx).pop()),
              ]),
            ]),
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _input.dispose();
    _inputFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _loadBrief() async {
    Map<String, dynamic>? brief;
    try {
      brief = await widget.client.getTodayBrief(timezone: await localTimezone());
    } catch (_) {
      brief = null;
    }
    if (!mounted) return;
    setState(() {
      _brief = brief;
      _briefLoaded = true;
    });
  }

  Future<void> _restoreChat() async {
    final prefs = await SharedPreferences.getInstance();
    final id = prefs.getString(_conversationKey);
    if (id == null) return;
    try {
      final rows = await widget.client.getChatHistory(conversationId: id);
      if (!mounted) return;
      setState(() {
        _conversationId = id;
        _messages
          ..clear()
          ..addAll(messagesFromHistory(rows));
      });
      _scrollToEnd();
    } catch (e) {
      if (mounted && isChatForbidden(e)) setState(() => _chatForbidden = true);
    }
  }

  Future<void> _send([String? text]) async {
    final message = (text ?? _input.text).trim();
    if (message.isEmpty || _streaming) return;
    _input.clear();
    setState(() {
      _messages.add(ChatMessage(fromUser: true, text: message));
      _lastError = null;
      _reply = const ChatReply();
      _streaming = true;
    });
    _scrollToEnd();
    try {
      await for (final event in widget.client.streamChat(message, conversationId: _conversationId)) {
        if (!mounted) return;
        setState(() => _reply = applyChatEvent(_reply!, event));
        _scrollToEnd();
      }
    } catch (e) {
      if (!mounted) return;
      if (isChatForbidden(e)) {
        setState(() {
          _chatForbidden = true;
          _streaming = false;
          _reply = null;
        });
        return;
      }
      setState(() => _reply = _reply!.copyWith(error: chatFailureText(e)));
    }
    if (!mounted) return;
    final reply = _reply!;
    setState(() {
      _streaming = false;
      _reply = null;
      if (reply.text.trim().isNotEmpty) {
        _messages.add(ChatMessage(fromUser: false, text: reply.text.trim()));
      }
      if (reply.error != null) _lastError = reply.error;
      if (reply.conversationId != null) _conversationId = reply.conversationId;
    });
    final id = reply.conversationId;
    if (id != null) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_conversationKey, id);
    }
    _inputFocus.requestFocus();
    _scrollToEnd();
  }

  /// The last send's failure, shown under the conversation until the next send.
  String? _lastError;

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(32, 36, 32, 40),
      children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1100),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Semantics(header: true, child: Text('Coach', style: SkyType.display(34))),
              const SizedBox(height: 18),
              LayoutBuilder(builder: (context, box) {
                final left = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  _letter(context),
                  const SizedBox(height: 18),
                  _weekPanel(context),
                ]);
                final chat = SizedBox(height: 640, child: _chatPanel(context));
                if (box.maxWidth < 860) {
                  return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    left,
                    const SizedBox(height: 18),
                    chat,
                  ]);
                }
                return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(flex: 3, child: left),
                  const SizedBox(width: 18),
                  Expanded(flex: 2, child: chat),
                ]);
              }),
            ]),
          ),
        ),
      ],
    );
  }

  // ── The letter ──

  Widget _letter(BuildContext context) {
    final p = context.sky;
    if (!_briefLoaded) {
      return const Panel(raised: true, child: SizedBox(height: 120, child: Center(child: CircularProgressIndicator())));
    }
    final parts = splitBrief(_brief?['body'] as String?);
    if (parts.headline == null && parts.blocks.isEmpty) {
      return Panel(
        raised: true,
        child: EmptyNote(
          icon: Icons.wb_twilight_rounded,
          title: 'No brief yet today',
          body: 'Your coach writes it from your recent days, in a few seconds, '
              'using a little of this month\'s coach budget.',
          action: SkyButton(
            label: _writing ? 'Writing…' : 'Write today\'s brief',
            icon: Icons.edit_note_rounded,
            kind: SkyButtonKind.primary,
            onPressed: _writing ? null : _writeBrief,
          ),
        ),
      );
    }
    final created = DateTime.tryParse(_brief?['created_at'] as String? ?? '')?.toLocal();
    final anchor = widget.week.complete ? widget.week.anchor?.project : null;
    return Panel(
      raised: true,
      color: p.panel.withValues(alpha: 1),
      padding: const EdgeInsets.fromLTRB(34, 30, 34, 28),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.wb_twilight_rounded, size: 22, color: p.sunInk),
          const SizedBox(width: 10),
          Text('Morning brief', style: SkyType.body(14, weight: FontWeight.w700).copyWith(color: p.sunInk)),
          const Spacer(),
          if (created != null)
            Text('${DateFormat('EEEE').format(created)} · ${formatTimeOfDay(created)}',
                style: SkyType.body(13).copyWith(color: p.inkMuted)),
        ]),
        const SizedBox(height: 16),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (parts.headline != null) ...[
              Semantics(
                header: true,
                child: Text(parts.headline!, style: SkyType.display(26).copyWith(height: 1.35)),
              ),
              const SizedBox(height: 14),
            ],
            for (final block in parts.blocks) _block(context, block),
          ]),
        ),
        const SizedBox(height: 14),
        Wrap(spacing: 10, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Text('Was this useful?', style: SkyType.body(13).copyWith(color: p.inkMuted)),
          for (final (rating, label, icon) in const [
            ('helpful', 'Helpful', Icons.thumb_up_alt_outlined),
            ('not_useful', 'Not useful', Icons.thumb_down_alt_outlined),
          ])
            Semantics(
              selected: _brief?['feedback'] == rating,
              child: SkyButton(
                label: label,
                icon: icon,
                kind: _brief?['feedback'] == rating ? SkyButtonKind.dark : SkyButtonKind.secondary,
                onPressed: () => _rate(rating),
              ),
            ),
        ]),
        if (anchor != null)
          ListenableBuilder(
            listenable: widget.timer,
            builder: (context, _) {
              if (widget.timer.current?.id == anchor.id) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(top: 10),
                child: SkyButton(
                  label: 'Start ${anchor.name}',
                  icon: Icons.play_arrow_rounded,
                  kind: SkyButtonKind.primary,
                  onPressed: () => TimerActions.start(context, widget.timer, anchor),
                ),
              );
            },
          ),
      ]),
    );
  }

  Widget _block(BuildContext context, BriefBlock block) {
    final p = context.sky;
    final body = SkyType.body(16, height: 1.8).copyWith(color: p.ink);
    TextSpan spans(TextStyle base) => TextSpan(children: [
          for (final s in block.spans)
            TextSpan(text: s.text, style: s.bold ? base.copyWith(fontWeight: FontWeight.w700) : base),
        ]);
    switch (block.kind) {
      case BriefBlockKind.heading:
        return Padding(
          padding: const EdgeInsets.only(top: 8, bottom: 6),
          child: Semantics(header: true, child: Text.rich(spans(SkyType.display(18)))),
        );
      case BriefBlockKind.bullet:
        return Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(
              padding: const EdgeInsets.only(top: 11, right: 12, left: 4),
              child: ProjectDot(color: p.sun, size: 6),
            ),
            Expanded(child: Text.rich(spans(body))),
          ]),
        );
      case BriefBlockKind.paragraph:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text.rich(spans(body)),
        );
    }
  }

  // ── The week ──

  Widget _weekPanel(BuildContext context) {
    final p = context.sky;
    return Panel(
      padding: const EdgeInsets.fromLTRB(26, 22, 26, 14),
      child: ListenableBuilder(
        listenable: widget.week,
        builder: (context, _) {
          final now = DateTime.now();
          final rows = [
            for (final w in widget.week.weeks)
              if (standingFor(w, now) case final s?) (w, s),
          ];
          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const PanelHeading('Where your week stands'),
            const SizedBox(height: 8),
            if (rows.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Text('Give a project a weekly goal on the web to see where it stands.',
                    style: SkyType.body(14).copyWith(color: p.inkMuted)),
              ),
            for (final (i, (w, s)) in rows.indexed)
              Container(
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  border: i == rows.length - 1 ? null : Border(bottom: BorderSide(color: p.hairline)),
                ),
                child: Row(children: [
                  ProjectDot(color: w.project.color),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text.rich(
                      TextSpan(children: [
                        TextSpan(text: w.project.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                        TextSpan(text: ' — ${s.sentence}'),
                      ]),
                      style: SkyType.body(15).copyWith(color: p.ink),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Chip2(
                    s.chip,
                    bold: true,
                    background: switch (s.tone) {
                      StandingTone.ahead => p.leaf.withValues(alpha: 0.14),
                      StandingTone.behind => p.persimmon.withValues(alpha: 0.14),
                      StandingTone.neutral => p.wash,
                    },
                    foreground: switch (s.tone) {
                      StandingTone.ahead => p.leafInk,
                      StandingTone.behind => p.persimmonInk,
                      StandingTone.neutral => p.ink,
                    },
                  ),
                ]),
              ),
          ]);
        },
      ),
    );
  }

  // ── Chat ──

  Widget _chatPanel(BuildContext context) {
    final p = context.sky;
    if (_chatForbidden) {
      return const Panel(
        child: Center(
          child: EmptyNote(
            icon: Icons.cloud_off_rounded,
            title: 'Chat needs a newer server',
            body: 'Update the LifePete server to chat with your coach from this Mac.',
          ),
        ),
      );
    }
    final reply = _reply;
    return Panel(
      padding: EdgeInsets.zero,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 8),
          child: Row(children: [
            Expanded(child: Semantics(header: true, child: Text('Ask', style: SkyType.display(19)))),
            if (memoryChipLabel(_memory) != null)
              ActionChip(
                label: Text(memoryChipLabel(_memory)!, style: SkyType.body(12)),
                backgroundColor: p.wash,
                side: BorderSide.none,
                shape: const StadiumBorder(),
                tooltip: 'What your coach remembers',
                onPressed: _showMemory,
              ),
          ]),
        ),
        Expanded(
          child: _messages.isEmpty && reply == null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Text(
                      'Ask about your time: your week, your focus, what to do next.',
                      textAlign: TextAlign.center,
                      style: SkyType.body(14).copyWith(color: p.inkMuted),
                    ),
                  ),
                )
              : ListView(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(18, 4, 18, 12),
                  children: [
                    for (final m in _messages) _bubble(context, fromUser: m.fromUser, text: m.text),
                    if (reply != null) _replyBubble(context, reply),
                    if (reply == null && _lastError != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(_lastError!, style: SkyType.body(13).copyWith(color: p.persimmonInk)),
                      ),
                  ],
                ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 8),
          child: Wrap(spacing: 8, runSpacing: 8, children: [
            for (final q in const ['How\'s my week going?', 'When do I focus best?'])
              OutlinedButton(
                onPressed: _streaming ? null : () => _sendSuggestion(q),
                style: OutlinedButton.styleFrom(
                  foregroundColor: p.ink,
                  side: BorderSide(color: p.hairline.withValues(alpha: 0.3)),
                  shape: const StadiumBorder(),
                  minimumSize: const Size(0, 34),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  textStyle: SkyType.body(13),
                ),
                child: Text(q),
              ),
          ]),
        ),
        Container(
          margin: const EdgeInsets.fromLTRB(14, 4, 14, 14),
          padding: const EdgeInsets.fromLTRB(16, 4, 6, 4),
          decoration: BoxDecoration(
            color: p.panel.withValues(alpha: 1),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: p.ink.withValues(alpha: 0.12)),
          ),
          child: Row(children: [
            Expanded(
              child: Focus(
                onKeyEvent: (node, event) {
                  if (event is KeyDownEvent &&
                      (event.logicalKey == LogicalKeyboardKey.enter ||
                          event.logicalKey == LogicalKeyboardKey.numpadEnter) &&
                      !HardwareKeyboard.instance.isShiftPressed) {
                    _send();
                    return KeyEventResult.handled;
                  }
                  return KeyEventResult.ignored;
                },
                child: TextField(
                  controller: _input,
                  focusNode: _inputFocus,
                  enabled: !_streaming,
                  minLines: 1,
                  maxLines: 4,
                  keyboardType: TextInputType.multiline,
                  style: SkyType.body(15).copyWith(color: p.ink),
                  decoration: const InputDecoration(
                    hintText: 'Ask about your time…',
                    filled: false,
                    border: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                    contentPadding: EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ),
            IconButton(
              tooltip: 'Send',
              onPressed: _streaming ? null : _send,
              icon: Icon(Icons.arrow_upward_rounded, color: p.onSun),
              style: IconButton.styleFrom(
                backgroundColor: p.sun,
                disabledBackgroundColor: p.sun.withValues(alpha: 0.4),
                fixedSize: const Size(40, 40),
              ),
            ),
          ]),
        ),
      ]),
    );
  }

  void _sendSuggestion(String q) => _send(q);

  Widget _bubble(BuildContext context, {required bool fromUser, required String text, Widget? child}) {
    final p = context.sky;
    return Align(
      alignment: fromUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: fromUser ? 360 : 420),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: fromUser ? p.ink : p.wash,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(20),
              topRight: const Radius.circular(20),
              bottomLeft: Radius.circular(fromUser ? 20 : 6),
              bottomRight: Radius.circular(fromUser ? 6 : 20),
            ),
          ),
          child: child ??
              SelectableText(
                text,
                style: SkyType.body(15, height: 1.6)
                    .copyWith(color: fromUser ? p.panel.withValues(alpha: 1) : p.ink),
              ),
        ),
      ),
    );
  }

  Widget _replyBubble(BuildContext context, ChatReply reply) {
    final p = context.sky;
    final muted = SkyType.body(14).copyWith(color: p.inkMuted, fontStyle: FontStyle.italic);
    return _bubble(
      context,
      fromUser: false,
      text: reply.text,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        if (reply.text.isNotEmpty) Text(reply.text, style: SkyType.body(15, height: 1.6).copyWith(color: p.ink)),
        if (reply.lookingUp)
          Padding(
            padding: EdgeInsets.only(top: reply.text.isEmpty ? 0 : 6),
            child: Text('Looking at your data…', style: muted),
          )
        else if (reply.text.isEmpty && reply.error == null)
          Text('…', style: muted),
        if (reply.error != null)
          Padding(
            padding: EdgeInsets.only(top: reply.text.isEmpty ? 0 : 6),
            child: Text(reply.error!, style: SkyType.body(14).copyWith(color: p.persimmonInk)),
          ),
      ]),
    );
  }
}
