/// Pure helper for building the deep link the companion's FlowScreen
/// opens when the user taps a BEST REPO / LANG / APP row.
///
/// Cross-language parity: matches the daemon's `buildInsightsURL` (Go,
/// daemon/cmd/beatsd/open.go) and the VS Code extension's
/// `buildInsightsUrl` (TS, integrations/vscode-beats/src/insightsUrl.ts).
/// All three produce byte-identical URLs given the same inputs so a
/// deep link from the companion, the editor, and `beatsd open` lands
/// on the same browser address bar.
library;

/// Filter axes that can land in the URL. All optional; empty filter
/// returns the bare /insights URL. AND-composed at the page level
/// via the web's useUrlParam.
class InsightsFilter {
  final String? repo;
  final String? language;
  final String? bundle;
  const InsightsFilter({this.repo, this.language, this.bundle});
}

/// Build the Insights deep link from the configured web base URL and
/// an optional filter.
///
/// - `base` is normalized: trailing slash stripped so the result is
///   always `<base>/insights` not `<base>//insights`.
/// - Filter values are URL-encoded so paths with spaces / `&` / `=`
///   round-trip safely.
/// - Param order is alphabetical (bundle, language, repo) — same as
///   the daemon's url.Values.Encode and the extension's
///   URLSearchParams insertion order. Two consecutive runs across
///   different surfaces produce byte-identical URLs.
String buildInsightsUrl(String base, [InsightsFilter? filter]) {
  final trimmed = base.endsWith('/') ? base.substring(0, base.length - 1) : base;
  final params = <String, String>{};
  if (filter?.bundle != null && filter!.bundle!.isNotEmpty) {
    params['bundle'] = filter.bundle!;
  }
  if (filter?.language != null && filter!.language!.isNotEmpty) {
    params['language'] = filter.language!;
  }
  if (filter?.repo != null && filter!.repo!.isNotEmpty) {
    params['repo'] = filter.repo!;
  }
  if (params.isEmpty) return '$trimmed/insights';
  // Build the query string with alphabetical key order. Dart's Uri
  // query encoding handles the value-side escaping.
  final sortedKeys = params.keys.toList()..sort();
  final query = sortedKeys
      .map((k) => '$k=${Uri.encodeQueryComponent(params[k]!)}')
      .join('&');
  return '$trimmed/insights?$query';
}
