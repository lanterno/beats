import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:beats_companion/services/recent_projects.dart';

void main() {
  // Each test resets the in-memory SharedPreferences store so order
  // dependencies don't sneak in. The plugin's setMockInitialValues lets
  // us provide a clean slate (or pre-populate when needed) without a
  // platform channel.
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('RecentProjects', () {
    test('load returns empty when nothing has been stored', () async {
      final recents = RecentProjects();
      expect(await recents.load(), isEmpty);
    });

    test('markUsed adds a single project id', () async {
      final recents = RecentProjects();
      await recents.markUsed('proj-1');
      expect(await recents.load(), ['proj-1']);
    });

    test('markUsed promotes an existing id to the head', () async {
      final recents = RecentProjects();
      await recents.markUsed('a');
      await recents.markUsed('b');
      await recents.markUsed('c');
      // Re-using 'a' should bring it to the front, not duplicate it.
      await recents.markUsed('a');
      expect(await recents.load(), ['a', 'c', 'b']);
    });

    test('markUsed dedupes — never stores the same id twice', () async {
      final recents = RecentProjects();
      await recents.markUsed('a');
      await recents.markUsed('a');
      await recents.markUsed('a');
      expect(await recents.load(), ['a']);
    });

    test('markUsed caps the list at 5 entries (most recent wins)', () async {
      final recents = RecentProjects();
      for (final id in ['a', 'b', 'c', 'd', 'e', 'f', 'g']) {
        await recents.markUsed(id);
      }
      // Order is most-recent-first, capped at 5: g, f, e, d, c.
      // 'a' and 'b' have aged out.
      expect(await recents.load(), ['g', 'f', 'e', 'd', 'c']);
    });

    test('markUsed("") is a no-op', () async {
      final recents = RecentProjects();
      await recents.markUsed('a');
      await recents.markUsed('');
      expect(await recents.load(), ['a']);
    });

    test('order persists across separate RecentProjects instances', () async {
      // Same SharedPreferences backing, two RecentProjects. The second
      // instance should see what the first wrote — pinning that the class
      // doesn't accidentally hold internal state.
      final first = RecentProjects();
      await first.markUsed('a');
      await first.markUsed('b');

      final second = RecentProjects();
      expect(await second.load(), ['b', 'a']);
    });
  });
}
