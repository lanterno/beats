import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:beats_companion/services/notification_dedupe.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('NotificationDedupe', () {
    test('alreadyNotified returns false on a fresh install', () async {
      final dedupe = NotificationDedupe();
      expect(await dedupe.alreadyNotified('brief', 'b-1'), isFalse);
    });

    test('markNotified then alreadyNotified returns true', () async {
      final dedupe = NotificationDedupe();
      await dedupe.markNotified('brief', 'b-1');
      expect(await dedupe.alreadyNotified('brief', 'b-1'), isTrue);
    });

    test('different ids of the same kind are not deduped against each other',
        () async {
      // Today's brief id 'b-1' fires; we mark it. Tomorrow's brief id 'b-2'
      // arrives; we should NOT see it as already-notified.
      final dedupe = NotificationDedupe();
      await dedupe.markNotified('brief', 'b-1');
      expect(await dedupe.alreadyNotified('brief', 'b-2'), isFalse);
    });

    test('marking a new id supersedes the old one for the same kind',
        () async {
      // Storage holds one id per kind; marking 'b-2' overwrites 'b-1'.
      // After that, even 'b-1' reads as not-notified (intentional — we
      // don't keep history, so re-running an old brief id will re-fire).
      final dedupe = NotificationDedupe();
      await dedupe.markNotified('brief', 'b-1');
      await dedupe.markNotified('brief', 'b-2');
      expect(await dedupe.alreadyNotified('brief', 'b-2'), isTrue);
      expect(await dedupe.alreadyNotified('brief', 'b-1'), isFalse);
    });

    test('different kinds dedupe independently', () async {
      // brief and review are separate channels — marking the same id
      // string under one kind shouldn't suppress the other.
      final dedupe = NotificationDedupe();
      await dedupe.markNotified('brief', '2026-04-30');
      expect(await dedupe.alreadyNotified('review', '2026-04-30'), isFalse);
    });

    test('persists across separate instances against the same prefs',
        () async {
      final first = NotificationDedupe();
      await first.markNotified('review', '2026-04-30');
      // A fresh instance (e.g. on app restart within the same session)
      // reads what the first wrote.
      final second = NotificationDedupe();
      expect(
        await second.alreadyNotified('review', '2026-04-30'),
        isTrue,
      );
    });
  });
}
