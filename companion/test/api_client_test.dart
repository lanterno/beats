// Tests for the companion's ApiException + envelope-parsing helper.
// Cross-surface parity: each case mirrors one in the daemon's
// describeErrorBody (Go) and the UI's ApiError 422-fields handling
// — a user hitting the same API failure on the web, the desktop
// companion, or the daemon CLI should see the same readable
// sentence rather than three different error styles.

import 'package:beats_companion/services/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('describeErrorBody', () {
    test('renders detail + code from the unified envelope', () {
      // The 4xx happy path — the envelope's detail message goes
      // first so a toast that just shows the suffix reads naturally,
      // and the code is bracketed so callers branching on it can
      // grep a log without false positives.
      expect(
        describeErrorBody(
          '{"detail":"Project archived","code":"PROJECT_ARCHIVED"}',
        ),
        'Project archived [PROJECT_ARCHIVED]',
      );
    });

    test('renders detail-only envelopes (older API versions)', () {
      // Pre-error-envelope FastAPI returned just `{detail}`. The
      // companion should still surface the human message rather
      // than collapsing to "(empty body)" or the raw JSON.
      expect(
        describeErrorBody('{"detail":"Invalid pairing code"}'),
        'Invalid pairing code',
      );
    });

    test('renders code-only envelopes', () {
      // Edge case — a router raises with a code but no message.
      // Better to see the code than nothing.
      expect(describeErrorBody('{"code":"RATE_LIMITED"}'), 'RATE_LIMITED');
    });

    test('appends 422 fields[] as "name (msg), email (msg)" suffix', () {
      // The whole point of this iteration: 422 validation errors
      // tell the user WHICH fields failed, not just "Validation
      // failed for 2 fields".
      const body =
          '{"detail":"Validation failed for 2 fields","code":"VALIDATION_ERROR",'
          '"fields":[{"path":"name","message":"field required","type":"missing"},'
          '{"path":"email","message":"invalid format","type":"value_error"}]}';
      expect(
        describeErrorBody(body),
        'Validation failed for 2 fields [VALIDATION_ERROR]: '
        'name (field required), email (invalid format)',
      );
    });

    test('skips entries in fields[] that have empty path AND message', () {
      // A hand-crafted server response with a blank entry shouldn't
      // produce "name (), email ()" — drop the empty entries
      // entirely.
      const body =
          '{"detail":"Validation failed","code":"VALIDATION_ERROR",'
          '"fields":[{"path":"","message":"","type":""}]}';
      expect(describeErrorBody(body), 'Validation failed [VALIDATION_ERROR]');
    });

    test('falls back to raw text on non-JSON bodies', () {
      // Proxy 502s often return HTML. The companion should surface
      // it (trimmed) so the user has SOMETHING to relay in a bug
      // report, rather than silently swallowing the body.
      expect(describeErrorBody('Bad Gateway\n'), 'Bad Gateway');
    });

    test('returns "(empty body)" for status-only failures', () {
      // A 503 with no body shouldn't end the toast with a trailing
      // colon followed by nothing — the suffix needs to read on its
      // own.
      expect(describeErrorBody(''), '(empty body)');
      expect(describeErrorBody('   '), '(empty body)');
    });

    test('falls back to raw JSON when shape is not an envelope', () {
      // Something JSON-shaped but not our envelope (e.g. older
      // FastAPI internals before the unified handler shipped).
      // Surface it raw so we don't silently lose context.
      expect(
        describeErrorBody('{"unrelated":"shape"}'),
        '{"unrelated":"shape"}',
      );
    });
  });

  group('ApiException', () {
    test('carries statusCode + message + optional code', () {
      final e = ApiException(404, 'Not found', code: 'PROJECT_NOT_FOUND');
      expect(e.statusCode, 404);
      expect(e.message, 'Not found');
      expect(e.code, 'PROJECT_NOT_FOUND');
    });

    test('code defaults to null when omitted', () {
      // Sites that pre-date the envelope (or non-API exceptions
      // synthesized by callers) shouldn't be forced to know about
      // the new field.
      expect(ApiException(500, 'kaboom').code, isNull);
    });

    test('toString embeds statusCode and message for log output', () {
      // Used in the companion's debug logs and a few SnackBars.
      // Locked in so a refactor that drops the "(N): " shape
      // doesn't break log greppability.
      expect(
        ApiException(401, 'Token expired').toString(),
        'ApiException(401): Token expired',
      );
    });
  });
}
