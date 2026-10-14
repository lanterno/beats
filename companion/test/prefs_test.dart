import 'package:beats_companion/state/prefs.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('Prefs', () {
    test('every notification kind is on for a fresh install', () async {
      SharedPreferences.setMockInitialValues({});
      final p = await Prefs.load();
      expect([p.briefOn, p.suggestOn, p.driftOn, p.holdingInFlow], everyElement(isTrue));
    });

    test('the old all-notifications switch, turned off, keeps every kind off', () async {
      SharedPreferences.setMockInitialValues({'beats_notifications_enabled': false});
      final p = await Prefs.load();
      expect([p.briefOn, p.suggestOn, p.driftOn], everyElement(isFalse));
    });

    test('a kind set on its own wins over the old switch', () async {
      SharedPreferences.setMockInitialValues({
        'beats_notifications_enabled': false,
        Prefs.notifyBrief: true,
      });
      final p = await Prefs.load();
      expect(p.briefOn, isTrue);
      expect(p.driftOn, isFalse);
    });

    test('an unknown menu bar setting reads as time and project', () async {
      SharedPreferences.setMockInitialValues({Prefs.menuBar: 'sparkles'});
      expect((await Prefs.load()).menuBarShows, MenuBarShows.timeAndProject);
    });
  });

  group('inFlow', () {
    test('needs five windows averaging 0.7', () {
      expect(inFlow([0.9, 0.9, 0.9, 0.9]), isFalse);
      expect(inFlow([0.7, 0.7, 0.7, 0.7, 0.7]), isTrue);
      expect(inFlow([0.9, 0.9, 0.9, 0.1, 0.1]), isFalse); // averages 0.58
      expect(inFlow(const []), isFalse);
    });
  });
}
