/// What the Coach screen says, kept apart from how it draws it: the brief
/// split into a headline and blocks, a sentence on where each project's week
/// stands, and the coach's streamed reply folded into one chat bubble.
library;

import '../state/week_controller.dart';
import 'api_client.dart';
import 'time_format.dart';

// ── The brief ──────────────────────────────────────────────────────────

enum BriefBlockKind { paragraph, heading, bullet }

/// A run of text, bold or not.
class BriefSpan {
  final String text;
  final bool bold;
  const BriefSpan(this.text, {this.bold = false});

  @override
  bool operator ==(Object other) => other is BriefSpan && other.text == text && other.bold == bold;

  @override
  int get hashCode => Object.hash(text, bold);

  @override
  String toString() => bold ? '**$text**' : text;
}

class BriefBlock {
  final BriefBlockKind kind;
  final List<BriefSpan> spans;
  const BriefBlock(this.kind, this.spans);

  String get plain => spans.map((s) => s.text).join();
}

class BriefParts {
  /// The line the letter opens with: the brief's own heading when it starts
  /// with one, else its first sentence. Null for an empty brief.
  final String? headline;
  final List<BriefBlock> blocks;
  const BriefParts(this.headline, this.blocks);
}

/// Splits **bold** runs out of [text] and drops the remaining emphasis and
/// code marks (`*`, `_`, backticks) a reader would otherwise see.
List<BriefSpan> parseSpans(String text) {
  final spans = <BriefSpan>[];
  final parts = text.split('**');
  for (var i = 0; i < parts.length; i++) {
    // An odd number of `**` leaves the last part unpaired: plain text.
    final bold = i.isOdd && i < parts.length - (parts.length.isEven ? 1 : 0);
    final cleaned = parts[i].replaceAll(RegExp(r'(?<!\w)[*_]|[*_](?!\w)|`'), '');
    if (cleaned.isEmpty) continue;
    spans.add(BriefSpan(cleaned, bold: bold));
  }
  return spans;
}

/// Reads a markdown-ish brief into blocks: `#` lines are headings, `-`, `*`
/// and `1.` lines are bullets, and consecutive other lines join into one
/// paragraph until a blank line.
BriefParts splitBrief(String? body) {
  if (body == null || body.trim().isEmpty) return const BriefParts(null, []);
  final raw = <(BriefBlockKind, String)>[];
  final para = <String>[];

  void flush() {
    if (para.isEmpty) return;
    raw.add((BriefBlockKind.paragraph, para.join(' ')));
    para.clear();
  }

  for (final source in body.split('\n')) {
    final line = source.trim();
    if (line.isEmpty) {
      flush();
      continue;
    }
    final heading = RegExp(r'^#+\s+(.*)$').firstMatch(line);
    final bullet = RegExp(r'^(?:[-*•]|\d+[.)])\s+(.*)$').firstMatch(line);
    if (heading != null) {
      flush();
      raw.add((BriefBlockKind.heading, heading.group(1)!));
    } else if (bullet != null) {
      flush();
      raw.add((BriefBlockKind.bullet, bullet.group(1)!));
    } else {
      para.add(line);
    }
  }
  flush();
  raw.removeWhere((b) => _plain(b.$2).isEmpty);
  if (raw.isEmpty) return const BriefParts(null, []);

  List<BriefBlock> blocks(Iterable<(BriefBlockKind, String)> rs) =>
      [for (final (kind, text) in rs) BriefBlock(kind, parseSpans(text))];

  final (kind, first) = raw.first;
  if (kind == BriefBlockKind.heading) return BriefParts(_plain(first), blocks(raw.skip(1)));
  if (kind == BriefBlockKind.bullet) return BriefParts(null, blocks(raw));

  // The opening sentence becomes the headline; the paragraph keeps the rest.
  final end = RegExp(r'[.!?](?=\s|\*|$)').firstMatch(first);
  if (end == null || _plain(first.substring(end.end)).isEmpty) {
    return BriefParts(_plain(first), blocks(raw.skip(1)));
  }
  var rest = first.substring(end.end).trimLeft();
  // The cut fell inside a bold run: the rest opens with its closing marks.
  if (rest.startsWith('**') && '**'.allMatches(first.substring(0, end.end)).length.isOdd) {
    rest = rest.substring(2).trimLeft();
  } else if ('**'.allMatches(first.substring(0, end.end)).length.isOdd) {
    rest = '**$rest';
  }
  return BriefParts(_plain(first.substring(0, end.end)), [
    BriefBlock(BriefBlockKind.paragraph, parseSpans(rest)),
    ...blocks(raw.skip(1)),
  ]);
}

String _plain(String text) => parseSpans(text).map((s) => s.text).join().trim();

// ── Where the week stands ─────────────────────────────────────────────

enum StandingTone { ahead, behind, neutral }

class WeekStanding {
  final String sentence;
  final String chip;
  final StandingTone tone;
  const WeekStanding(this.sentence, this.chip, this.tone);
}

/// One line on [w] as of [now], or null for a project with no target.
///
/// A day job is measured against its target spread Monday to Friday through
/// today: what is still missing from that is "more today keeps this week on pace".
/// Its chip is the balance since the contract began, which is why it says
/// "overall": a week can be behind while the balance is ahead. Any other target is a goal for the week: hours
/// of the goal, and a percentage.
WeekStanding? standingFor(ProjectWeek w, DateTime now) {
  final target = w.target;
  if (target == null || target <= 0) return null;
  final worked = (w.worked * 60).round();
  final goal = (target * 60).round();

  if (w.project.kind == 'day_job') {
    final workdays = now.weekday > 5 ? 5 : now.weekday;
    final dueSoFar = (target * workdays / 5 * 60).round();
    final missing = dueSoFar - worked;
    final sentence = missing > 0
        ? '${formatMinutes(missing)} more today keeps this week on pace'
        : 'This week is on pace';
    final balance = w.balance;
    if (balance != null) {
      return WeekStanding(
        sentence,
        '${formatBalance(balance)} overall',
        (balance * 60).round() >= 0 ? StandingTone.ahead : StandingTone.behind,
      );
    }
    return WeekStanding(sentence, '${(worked / goal * 100).round()}%', StandingTone.neutral);
  }

  final pct = (worked / goal * 100).round();
  if (worked >= goal) {
    return WeekStanding(
      'Goal reached: ${formatMinutes(worked)} of ${formatMinutes(goal)}',
      '$pct%',
      StandingTone.ahead,
    );
  }
  return WeekStanding('${formatMinutes(worked)} of your ${formatMinutes(goal)} goal', '$pct%', StandingTone.neutral);
}

// ── Chat ───────────────────────────────────────────────────────────────

const budgetReachedMessage = 'You\'ve reached this month\'s coach budget.';

/// The coach's reply as it streams in.
class ChatReply {
  final String text;

  /// A tool call is in flight: the coach is reading the user's data.
  final bool lookingUp;
  final String? error;
  final String? conversationId;
  final bool done;

  const ChatReply({
    this.text = '',
    this.lookingUp = false,
    this.error,
    this.conversationId,
    this.done = false,
  });

  ChatReply copyWith({String? text, bool? lookingUp, String? error, String? conversationId, bool? done}) =>
      ChatReply(
        text: text ?? this.text,
        lookingUp: lookingUp ?? this.lookingUp,
        error: error ?? this.error,
        conversationId: conversationId ?? this.conversationId,
        done: done ?? this.done,
      );
}

/// Folds one SSE event from `/api/coach/chat` into [reply]. Unknown event
/// types leave it as it was.
ChatReply applyChatEvent(ChatReply reply, Map<String, dynamic> event) {
  switch (event['type']) {
    case 'text':
      final t = event['text'];
      return reply.copyWith(text: reply.text + (t is String ? t : ''), lookingUp: false);
    case 'tool_use':
      return reply.copyWith(lookingUp: true);
    case 'tool_result':
      return reply.copyWith(lookingUp: false);
    case 'error':
      final code = event['code'];
      final message = code == 429
          ? budgetReachedMessage
          : (event['error'] is String && (event['error'] as String).isNotEmpty
              ? event['error'] as String
              : 'The coach is unavailable right now.');
      return reply.copyWith(error: message, lookingUp: false);
    case 'done':
      final id = event['conversation_id'];
      return reply.copyWith(conversationId: id is String ? id : null, done: true, lookingUp: false);
    default:
      return reply;
  }
}

/// Folds a whole event sequence, as the screen does one event at a time.
ChatReply foldChatEvents(Iterable<Map<String, dynamic>> events) =>
    events.fold(const ChatReply(), applyChatEvent);

/// A server too old to let a paired device chat answers 403.
bool isChatForbidden(Object error) => error is ApiException && error.statusCode == 403;

/// What to show for a send that failed before any reply streamed.
String chatFailureText(Object error) {
  if (error is ApiException && (error.statusCode == 429 || error.code == 'BUDGET_EXCEEDED')) {
    return budgetReachedMessage;
  }
  return 'Couldn\'t reach the coach. Try again in a moment.';
}

class ChatMessage {
  final bool fromUser;
  final String text;
  const ChatMessage({required this.fromUser, required this.text});
}

/// The stored conversation as bubbles: user and assistant turns with text,
/// in order; tool turns and empty content are left out.
List<ChatMessage> messagesFromHistory(List<Map<String, dynamic>> rows) => [
      for (final r in rows)
        if ((r['role'] == 'user' || r['role'] == 'assistant') &&
            r['content'] is String &&
            (r['content'] as String).trim().isNotEmpty)
          ChatMessage(fromUser: r['role'] == 'user', text: (r['content'] as String).trim()),
    ];
