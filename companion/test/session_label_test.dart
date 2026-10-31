// What a session's bar on Today's strip says. A session a decider logged
// for the member carries `entered_by` and is marked "entered for you" in
// the web app's timeline (TodayFeed, WeekDays); the companion says the same
// words after the project's name (docs/organisations.md, decision 24).

import 'package:beats_companion/services/day_ribbon.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test("the member's own session is the project's name alone", () {
    expect(sessionLabel('Platform'), 'Platform');
    expect(sessionLabel('Platform', enteredBy: null), 'Platform');
  });

  test("a session a decider entered is marked in the web app's words", () {
    expect(sessionLabel('Platform', enteredBy: 'u-manager'), 'Platform · entered for you');
  });

  test('an empty stamp is no stamp, as the web app reads it', () {
    expect(sessionLabel('Platform', enteredBy: ''), 'Platform');
  });
}
