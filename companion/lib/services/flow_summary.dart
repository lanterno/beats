/// Pure parser for the /api/signals/flow-windows/summary response shape
/// — converts the loosely-typed JSON map into a strongly-typed
/// FlowHeadline (or null when there's nothing to display).
///
/// Lives outside the widgets so the field-extraction edge cases (null
/// fields, num types that need toDouble, count=0) can be unit tested
/// without rendering a screen. Currently used by FlowScreen's
/// "best repo / best language today" line and CoachScreen's flow
/// headline strip; future companion screens consuming /summary should
/// route through this rather than re-parsing the raw map.
library;

/// The compact view of /summary the companion's headline UIs display.
/// Numbers are pre-rounded to integer percent points (0-100) so the
/// widgets don't have to do arithmetic themselves.
class FlowHeadline {
  final int avg;
  final int peak;
  final int count;
  final String? topRepo;
  final String? topLanguage;
  final String? topBundle;

  const FlowHeadline({
    required this.avg,
    required this.peak,
    required this.count,
    this.topRepo,
    this.topLanguage,
    this.topBundle,
  });
}

/// Parses a /summary JSON map into a FlowHeadline, or null when the
/// map is missing / count is zero. The "no data" case returns null
/// rather than a zero-valued record so callers don't accidentally
/// render "avg 0" — same rule the VS Code status bar follows.
FlowHeadline? parseFlowSummary(Map<String, dynamic>? raw) {
  if (raw == null) return null;
  final count = (raw['count'] as num?)?.toInt() ?? 0;
  if (count <= 0) return null;
  final avg = (((raw['avg'] as num?)?.toDouble() ?? 0.0) * 100).round();
  final peak = (((raw['peak'] as num?)?.toDouble() ?? 0.0) * 100).round();
  return FlowHeadline(
    avg: avg,
    peak: peak,
    count: count,
    topRepo: (raw['top_repo'] as Map?)?['key'] as String?,
    topLanguage: (raw['top_language'] as Map?)?['key'] as String?,
    topBundle: (raw['top_bundle'] as Map?)?['key'] as String?,
  );
}
