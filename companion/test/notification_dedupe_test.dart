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

    test('marking a second id keeps the first remembered for the same kind',
        () async {
      // The dedupe remembers multiple recent ids per kind, so marking
      // 'b-2' must NOT evict 'b-1' — both still read as notified. This is
      // the core fix: list-shaped kinds mark many ids per tick without
      // clobbering each other.
      final dedupe = NotificationDedupe();
      await dedupe.markNotified('brief', 'b-1');
      await dedupe.markNotified('brief', 'b-2');
      expect(await dedupe.alreadyNotified('brief', 'b-2'), isTrue);
      expect(await dedupe.alreadyNotified('brief', 'b-1'), isTrue);
    });

    test('a multi-event tick marks every id; none re-fire next tick',
        () async {
      // Simulates _pollDrift / _pollAutoTimer: a single tick iterates a
      // list of events and marks each. On the next tick every still-present
      // id must read as already-notified (the regression we fixed).
      final dedupe = NotificationDedupe();
      final tick = ['d-1', 'd-2', 'd-3', 'd-4', 'd-5'];
      for (final id in tick) {
        await dedupe.markNotified('drift', id);
      }
      for (final id in tick) {
        expect(await dedupe.alreadyNotified('drift', id), isTrue,
            reason: '$id should still be deduped after a full-list tick');
      }
      // A brand-new event in a later tick still fires.
      expect(await dedupe.alreadyNotified('drift', 'd-6'), isFalse);
    });

    test('per-kind storage is bounded — oldest ids are evicted', () async {
      // Mark well past the cap; the earliest ids fall off while the most
      // recent are retained, so the prefs key can't grow without bound.
      final dedupe = NotificationDedupe();
      for (var i = 0; i < 200; i++) {
        await dedupe.markNotified('drift', 'd-$i');
      }
      // Oldest evicted.
      expect(await dedupe.alreadyNotified('drift', 'd-0'), isFalse);
      // Most recent retained.
      expect(await dedupe.alreadyNotified('drift', 'd-199'), isTrue);
      expect(await dedupe.alreadyNotified('drift', 'd-198'), isTrue);
    });

    test('re-marking an id refreshes its recency without duplicating',
        () async {
      // Re-marking moves an id to newest so it survives eviction longer; it
      // must not be stored twice.
      final dedupe = NotificationDedupe();
      await dedupe.markNotified('drift', 'keep');
      for (var i = 0; i < 60; i++) {
        await dedupe.markNotified('drift', 'd-$i');
      }
      // Refresh 'keep' so it's newest again.
      await dedupe.markNotified('drift', 'keep');
      for (var i = 60; i < 120; i++) {
        await dedupe.markNotified('drift', 'd-$i');
      }
      expect(await dedupe.alreadyNotified('drift', 'keep'), isTrue);
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
