// A session a decider logged for the member is marked "entered for you"
// (docs/organisations.md, decision 24). The mark is the notification —
// nothing else tells the member a session they did not start appeared on
// their timeline — so every surface that shows the session owes it, in the
// same words the web's timeline uses (`TodayFeed.tsx`, `WeekDays.tsx`).
// The companion showed the session and no mark until #421.

import 'package:beats_companion/services/day_ribbon.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a session the member started is its project, and nothing more', () {
    expect(sessionLabel('Platform'), 'Platform');
    expect(sessionLabel('Platform', enteredBy: null), 'Platform');
  });

  test('a session a decider entered carries the web\'s wording', () {
    expect(sessionLabel('Platform', enteredBy: 'u-admin'), 'Platform · entered for you');
  });

  test('a project the timer cannot name is still a session', () {
    expect(sessionLabel(null), 'Session');
    expect(sessionLabel(''), 'Session');
    expect(sessionLabel(null, enteredBy: 'u-admin'), 'Session · entered for you');
  });

  test('an empty entered_by is no decider, as an absent one is', () {
    expect(sessionLabel('Platform', enteredBy: ''), 'Platform');
  });
}
