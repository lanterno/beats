// Cross-language parity check: each assertion mirrors a case in
// integrations/vscode-beats/src/insightsUrl.test.ts (TS) and
// daemon/cmd/beatsd/open_test.go (Go). A deep link from the
// companion, the VS Code extension, and `beatsd open` should produce
// byte-identical URLs given the same inputs.

import 'package:beats_companion/services/insights_url.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('buildInsightsUrl', () {
    test('returns the bare /insights URL when no filter is given', () {
      expect(buildInsightsUrl('http://localhost:8080'), 'http://localhost:8080/insights');
      expect(
          buildInsightsUrl('http://localhost:8080', const InsightsFilter()),
          'http://localhost:8080/insights');
    });

    test('appends ?repo=<encoded path> when a workspace is set', () {
      expect(
        buildInsightsUrl(
            'http://localhost:8080', const InsightsFilter(repo: '/Users/me/code/beats')),
        'http://localhost:8080/insights?repo=%2FUsers%2Fme%2Fcode%2Fbeats',
      );
    });

    test('strips a trailing slash on the base URL so we never produce //insights', () {
      // Self-hosted users sometimes set webUrl with a trailing slash.
      // Normalize to match the daemon + extension.
      expect(
        buildInsightsUrl('https://beats.example.com/'),
        'https://beats.example.com/insights',
      );
      expect(
        buildInsightsUrl('https://beats.example.com/', const InsightsFilter(repo: '/code/x')),
        'https://beats.example.com/insights?repo=%2Fcode%2Fx',
      );
    });

    test('treats null/empty repo as no workspace', () {
      expect(
        buildInsightsUrl('http://localhost:8080', const InsightsFilter(repo: null)),
        'http://localhost:8080/insights',
      );
      expect(
        buildInsightsUrl('http://localhost:8080', const InsightsFilter(repo: '')),
        'http://localhost:8080/insights',
      );
    });

    test('URL-encodes paths with spaces and special characters', () {
      // Paths with spaces happen on macOS; & / = are pathological but
      // possible. The web's useUrlParam reads via URLSearchParams.get
      // which decodes — verify the encoding chain matches.
      final url = buildInsightsUrl(
          'http://localhost:8080',
          const InsightsFilter(repo: '/Users/me/My Code/x&y=z'));
      final parsed = Uri.parse(url);
      expect(parsed.path, '/insights');
      expect(parsed.queryParameters['repo'], '/Users/me/My Code/x&y=z');
    });

    test('appends ?language=<id> when only language is set', () {
      final url = buildInsightsUrl('http://localhost:8080', const InsightsFilter(language: 'go'));
      expect(Uri.parse(url).queryParameters['language'], 'go');
    });

    test('appends ?bundle=<id> when only bundle is set', () {
      final url = buildInsightsUrl(
          'http://localhost:8080', const InsightsFilter(bundle: 'com.microsoft.VSCode'));
      expect(Uri.parse(url).queryParameters['bundle'], 'com.microsoft.VSCode');
    });

    test('composes all three axes in the URL', () {
      final url = buildInsightsUrl(
        'http://localhost:8080',
        const InsightsFilter(
          repo: '/Users/me/code/beats',
          language: 'go',
          bundle: 'com.microsoft.VSCode',
        ),
      );
      final params = Uri.parse(url).queryParameters;
      expect(params['repo'], '/Users/me/code/beats');
      expect(params['language'], 'go');
      expect(params['bundle'], 'com.microsoft.VSCode');
    });

    test('orders keys alphabetically — bundle, language, repo — for stable URLs', () {
      // Same rule as the daemon's url.Values.Encode and the
      // extension's URLSearchParams insertion order. Two consecutive
      // runs across different surfaces produce byte-identical URLs
      // (matters for clipboard diffs, shell history grepping, and
      // user-shared deep links).
      final url = buildInsightsUrl(
        'http://localhost:8080',
        const InsightsFilter(repo: 'r', language: 'l', bundle: 'b'),
      );
      expect(url, 'http://localhost:8080/insights?bundle=b&language=l&repo=r');
    });
  });
}
