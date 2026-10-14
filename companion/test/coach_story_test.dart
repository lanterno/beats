import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/services/coach_story.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:beats_companion/state/week_controller.dart';
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';

const dayJob = Project(id: 'p1', name: 'Northwind', color: Color(0xFF4F8FD6), kind: 'day_job');
const side = Project(id: 'p2', name: 'LifePete', color: Color(0xFF8E7CC3), kind: 'side_project');

ProjectWeek week(Project p, {required double worked, double? target, double? balance}) =>
    ProjectWeek(project: p, worked: worked, days: List.filled(7, 0), target: target, balance: balance);

void main() {
  group('splitBrief', () {
    test('the first sentence becomes the headline and the paragraph keeps the rest', () {
      final b = splitBrief('Protect the morning. The afternoon is spoken for.\n\nSecond paragraph.');
      expect(b.headline, 'Protect the morning.');
      expect(b.blocks.map((x) => x.plain), ['The afternoon is spoken for.', 'Second paragraph.']);
    });

    test('a leading heading is the headline', () {
      final b = splitBrief('## A calm Wednesday\nOnly one meeting today.');
      expect(b.headline, 'A calm Wednesday');
      expect(b.blocks.single.plain, 'Only one meeting today.');
    });

    test('a one-sentence paragraph is all headline', () {
      final b = splitBrief('Rest today.\n\n- Walk\n- Read');
      expect(b.headline, 'Rest today.');
      expect(b.blocks.map((x) => x.kind), [BriefBlockKind.bullet, BriefBlockKind.bullet]);
    });

    test('lines without a blank between them are one paragraph', () {
      final b = splitBrief('Headline here.\nline one\nline two');
      expect(b.blocks.single.plain, 'line one line two');
    });

    test('bold survives the cut and emphasis marks go', () {
      final b = splitBrief('Start early. Your **best flow** came _before_ 11.');
      expect(b.blocks.single.spans, const [
        BriefSpan('Your '),
        BriefSpan('best flow', bold: true),
        BriefSpan(' came before 11.'),
      ]);
    });

    test('a headline cut inside a bold run leaves the rest correctly bold', () {
      final b = splitBrief('**Big day. Two launches** and a review.');
      expect(b.headline, 'Big day.');
      expect(b.blocks.single.spans.first, const BriefSpan('Two launches', bold: true));
    });

    test('an unpaired ** is shown as plain text, not swallowing the rest', () {
      expect(parseSpans('a **b'), const [BriefSpan('a '), BriefSpan('b')]);
    });

    test('nothing to read', () {
      expect(splitBrief(null).headline, isNull);
      expect(splitBrief('  \n\n ').blocks, isEmpty);
    });
  });

  group('standingFor', () {
    final wednesday = DateTime(2026, 10, 14, 11);

    test('a day job behind its pace says what today still needs, with its balance', () {
      // 40h over five days: 24h due through Wednesday, 19h 34m worked.
      final s = standingFor(week(dayJob, worked: 19 + 34 / 60, target: 40, balance: 1 + 10 / 60), wednesday)!;
      expect(s.sentence, '4h 26m more today keeps this week on pace');
      expect(s.chip, '+1h 10m overall');
      expect(s.tone, StandingTone.ahead);
    });

    test('a day job past its pace is on pace, and a negative balance is behind', () {
      final s = standingFor(week(dayJob, worked: 25, target: 40, balance: -0.5), wednesday)!;
      expect(s.sentence, 'This week is on pace');
      expect(s.tone, StandingTone.behind);
    });

    test('on a weekend a day job is measured against the whole week', () {
      final s = standingFor(week(dayJob, worked: 38, target: 40), DateTime(2026, 10, 17))!;
      expect(s.sentence, '2h more today keeps this week on pace');
      expect(s.chip, '95%');
    });

    test('a goal reads as hours of the goal and a percentage', () {
      final s = standingFor(week(side, worked: 6 + 5 / 60, target: 8), wednesday)!;
      expect(s.sentence, '6h 05m of your 8h goal');
      expect(s.chip, '76%');
      expect(s.tone, StandingTone.neutral);
    });

    test('a goal met says so', () {
      final s = standingFor(week(side, worked: 9, target: 8), wednesday)!;
      expect(s.sentence, 'Goal reached: 9h of 8h');
      expect(s.tone, StandingTone.ahead);
    });

    test('no target, no row', () {
      expect(standingFor(week(side, worked: 3), wednesday), isNull);
      expect(standingFor(week(side, worked: 3, target: 0), wednesday), isNull);
    });
  });

  group('applyChatEvent', () {
    test('text accumulates and done carries the conversation id', () {
      final r = foldChatEvents([
        {'type': 'text', 'text': 'Two '},
        {'type': 'text', 'text': 'meetings.'},
        {'type': 'done', 'conversation_id': 'c9'},
      ]);
      expect(r.text, 'Two meetings.');
      expect(r.conversationId, 'c9');
      expect(r.done, isTrue);
    });

    test('a tool call shows as looking up until text or its result arrives', () {
      var r = applyChatEvent(const ChatReply(), {'type': 'tool_use', 'name': 'get_week'});
      expect(r.lookingUp, isTrue);
      r = applyChatEvent(r, {'type': 'tool_result', 'name': 'get_week'});
      expect(r.lookingUp, isFalse);
      r = applyChatEvent(applyChatEvent(r, {'type': 'tool_use'}), {'type': 'text', 'text': 'x'});
      expect(r.lookingUp, isFalse);
    });

    test('a budget error reads as the budget, other errors as sent', () {
      expect(applyChatEvent(const ChatReply(), {'type': 'error', 'error': 'x', 'code': 429}).error,
          budgetReachedMessage);
      expect(applyChatEvent(const ChatReply(), {'type': 'error', 'error': 'Coach is down.', 'code': 502}).error,
          'Coach is down.');
    });

    test('a later done keeps the text and an earlier id is not lost to a missing one', () {
      final r = applyChatEvent(const ChatReply(text: 'hi', conversationId: 'c1'), {'type': 'done'});
      expect(r.text, 'hi');
      expect(r.conversationId, 'c1');
    });

    test('unknown events change nothing', () {
      const r = ChatReply(text: 'a');
      expect(identical(applyChatEvent(r, {'type': 'ping'}), r), isTrue);
    });
  });

  group('chat failures', () {
    test('only a 403 means the server does not let devices chat', () {
      expect(isChatForbidden(ApiException(403, 'x', code: 'DEVICE_PATH_FORBIDDEN')), isTrue);
      expect(isChatForbidden(ApiException(500, 'x')), isFalse);
      expect(isChatForbidden(Exception('offline')), isFalse);
    });

    test('a budget refusal before the stream reads as the budget', () {
      expect(chatFailureText(ApiException(429, 'x', code: 'BUDGET_EXCEEDED')), budgetReachedMessage);
      expect(chatFailureText(Exception('offline')), contains('Try again'));
    });
  });

  test('history keeps user and assistant turns with text, in order', () {
    final m = messagesFromHistory([
      {'role': 'user', 'content': 'Why?'},
      {'role': 'tool', 'content': '{}'},
      {'role': 'assistant', 'content': '  '},
      {'role': 'assistant', 'content': 'Because.'},
    ]);
    expect(m.map((x) => (x.fromUser, x.text)), [(true, 'Why?'), (false, 'Because.')]);
  });
}
