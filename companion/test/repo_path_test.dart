// Tests for shortRepoTail. Cross-language parity check: every
// assertion here should match the equivalent behavior in the Go
// daemon's shortRepoTrail (daemon/cmd/beatsd/recent.go) and the
// web's shortRepoPath (ui/client/shared/lib/flowAggregation.ts).

import 'package:beats_companion/services/repo_path.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('shortRepoTail', () {
    test('returns the last two path segments for nested paths', () {
      expect(shortRepoTail('/Users/me/code/beats'), 'code/beats');
    });

    test('returns the original when there are fewer than three segments', () {
      // Two-segment path stays as-is — no `slice(-2)` weirdness that
      // would drop the leading slash.
      expect(shortRepoTail('a/b'), 'a/b');
    });

    test('returns empty input unchanged', () {
      expect(shortRepoTail(''), '');
    });

    test('handles Windows-style backslash separators', () {
      // The daemon's Go test asserts the same behavior; users on
      // Windows hosts shouldn't see literal backslashes in the
      // shortened display.
      expect(shortRepoTail(r'C:\Users\me\code\beats'), 'code/beats');
    });

    test('collapses repeated separators (e.g. "//" or "\\\\")', () {
      // FieldsFunc / split-with-empty-filter dedupes runs; verify
      // the Dart version matches.
      expect(shortRepoTail('//Users//me//code//beats'), 'code/beats');
    });

    test('single-segment path returns unchanged', () {
      expect(shortRepoTail('beats'), 'beats');
    });

    test('preserves a leading slash on a two-segment absolute path', () {
      // Subtle parity choice: the Dart version matches Go's
      // shortRepoTrail (returns the original) — NOT the web's
      // shortRepoPath (which would strip the leading slash and return
      // "users/me"). The daemon is the main producer of these paths
      // and its display expectation wins here. If a future ship
      // wants to align all three, do it once across all languages.
      expect(shortRepoTail('/users/me'), '/users/me');
    });
  });
}
