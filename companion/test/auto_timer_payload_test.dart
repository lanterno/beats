// Tests for parseAutoTimerPayload — the pure encoding contract for the
// auto-timer notification payload. Locks in the `auto-timer:<id>|<name>`
// shape so the tap router (POSTs /api/timer/start with the parsed id)
// can't silently break when notifications.dart is refactored.

import 'package:beats_companion/services/notifications.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('parseAutoTimerPayload — happy path', () {
    test('parses a normal id|name payload', () {
      final parsed = parseAutoTimerPayload('auto-timer:proj_123|Beats Companion');
      expect(parsed, isNotNull);
      expect(parsed!.projectId, 'proj_123');
      expect(parsed.projectName, 'Beats Companion');
    });

    test('keeps embedded pipes in the project name', () {
      // Project names are user-supplied; if one happens to contain `|`,
      // splitting on the first separator preserves the rest as-is. Locks
      // in the rule so a future refactor to `split('|').last` doesn't
      // silently truncate names like "Frontend | Mobile".
      final parsed = parseAutoTimerPayload('auto-timer:abc|Frontend | Mobile');
      expect(parsed, isNotNull);
      expect(parsed!.projectId, 'abc');
      expect(parsed.projectName, 'Frontend | Mobile');
    });

    test('accepts an id with no separator (empty name)', () {
      // Defensive: if the encoder ever drops the `|` (e.g. when
      // project_name is empty server-side), still produce a usable id.
      // The tap router uses an empty name to fall back to "project" in
      // its toast.
      final parsed = parseAutoTimerPayload('auto-timer:proj_only');
      expect(parsed, isNotNull);
      expect(parsed!.projectId, 'proj_only');
      expect(parsed.projectName, '');
    });
  });

  group('parseAutoTimerPayload — rejects invalid', () {
    test('null payload', () {
      // The flutter_local_notifications response.payload is nullable;
      // null in → null out so the router can early-exit.
      expect(parseAutoTimerPayload(null), isNull);
    });

    test('payload without the auto-timer prefix', () {
      // Other payloads (`brief`, `review`, `eod-mood`, `drift:...`)
      // should NOT match — the router routes them differently.
      expect(parseAutoTimerPayload('brief'), isNull);
      expect(parseAutoTimerPayload('review'), isNull);
      expect(parseAutoTimerPayload('drift:com.spotify.client'), isNull);
      expect(parseAutoTimerPayload(''), isNull);
    });

    test('auto-timer prefix but empty id', () {
      // The id is required to actually start the timer — without it the
      // action button would POST /api/timer/start with no project,
      // which 422s. Reject at the parser instead.
      expect(parseAutoTimerPayload('auto-timer:'), isNull);
      expect(parseAutoTimerPayload('auto-timer:|some-name'), isNull);
    });
  });
}
