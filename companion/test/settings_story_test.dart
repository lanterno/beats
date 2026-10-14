import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/services/settings_story.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime.utc(2026, 10, 14, 11, 5);

  group('signalAgo', () {
    test('seconds, then minutes, then hours', () {
      expect(signalAgo(now.subtract(const Duration(seconds: 2)), now), 'just now');
      expect(signalAgo(now.subtract(const Duration(seconds: 45)), now), '45s ago');
      expect(signalAgo(now.subtract(const Duration(minutes: 3, seconds: 59)), now), '3m ago');
      expect(signalAgo(now.subtract(const Duration(hours: 2, minutes: 10)), now), '2h ago');
    });

    test('a signal from the future (clock skew) is just now', () {
      expect(signalAgo(now.add(const Duration(minutes: 1)), now), 'just now');
    });

    test('compares instants, not wall clocks, across time zones', () {
      final local = now.subtract(const Duration(seconds: 30)).toLocal();
      expect(signalAgo(local, now), '30s ago');
    });
  });

  group('newestWindowEnd', () {
    test('picks the latest end and skips what does not parse', () {
      final newest = newestWindowEnd([
        {'window_end': '2026-10-14T11:00:00Z'},
        {'window_end': 'garbage'},
        {'window_end': '2026-10-14T11:04:00Z'},
        {},
      ]);
      expect(newest, DateTime.utc(2026, 10, 14, 11, 4));
      expect(newestWindowEnd(const []), isNull);
    });
  });

  group('workspaceCount', () {
    test('counts distinct repos, ignoring blanks and windows without one', () {
      expect(
        workspaceCount([
          {'editor_repo': 'beats'},
          {'editor_repo': ' beats '},
          {'editor_repo': 'kite'},
          {'editor_repo': ''},
          {'editor_repo': null},
          {},
        ]),
        2,
      );
    });
  });

  group('errors', () {
    test('a 403 means the server is older than the app', () {
      expect(needsNewerServer(ApiException(403, 'Oura status failed: forbidden')), isTrue);
      expect(needsNewerServer(ApiException(500, 'x')), isFalse);
      expect(needsNewerServer(StateError('x')), isFalse);
    });

    test('shortError drops the verb prefix and caps the length', () {
      expect(shortError(ApiException(502, 'Heartbeat failed: Bad gateway')), 'Bad gateway');
      final long = shortError(ApiException(500, 'Heartbeat failed: ${'x' * 200}'), max: 20);
      expect(long.length, 20);
      expect(long.endsWith('…'), isTrue);
    });
  });
}
