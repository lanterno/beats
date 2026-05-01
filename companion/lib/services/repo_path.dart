/// Pure helpers for displaying editor_repo paths. Lives outside the
/// widgets so the same logic can be unit tested without spinning up
/// a FlowScreen state.
///
/// Cross-language parity: matches the daemon's `shortRepoTrail`
/// (daemon/cmd/beatsd/recent.go) and the web's `shortRepoPath`
/// (ui/client/shared/lib/flowAggregation.ts) — three implementations
/// in three languages, kept consistent so users see the same
/// shortened path everywhere they look.
library;

/// Returns the last two path segments of an editor_repo so a deeply-
/// nested workspace stays readable in a single row. Falls back to the
/// original string when there are fewer than three segments. Handles
/// both Unix-style `/` and Windows-style `\` separators.
String shortRepoTail(String repo) {
  final parts =
      repo.split(RegExp(r'[\\/]')).where((p) => p.isNotEmpty).toList();
  if (parts.length <= 2) return repo;
  return parts.skip(parts.length - 2).join('/');
}
