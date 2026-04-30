/// Pure helpers for normalizing user-entered tags. Lives outside the
/// widget so the post-stop sheet's tag merging can be unit tested
/// without flutter_test having to mount a sheet.
library;

/// Splits a raw freeform tag string on commas + whitespace, lowercases,
/// drops empties, dedupes. The order of the result is stable to
/// `LinkedHashSet` iteration order so callers that show a chip preview
/// see the same order they typed in.
List<String> parseTagsInput(String raw) {
  final out = <String>{};
  for (final piece in raw.split(RegExp(r'[,\s]+'))) {
    final t = piece.trim().toLowerCase();
    if (t.isNotEmpty) out.add(t);
  }
  return out.toList();
}

/// Merges a set of pre-selected chip tags with freeform-typed tags. The
/// post-stop sheet uses both: the user can tap chips of recent tags AND
/// type new ones. We dedupe the union (chips might overlap with what
/// they typed) and preserve a stable order: chip selections first
/// (in the iteration order they were toggled), then any new typed tags
/// in input order.
List<String> mergeTags({required Iterable<String> chips, required Iterable<String> typed}) {
  final out = <String>{};
  // Normalize chip ids the same way typed entries are normalized so
  // `Coding` and `coding` don't both end up in the result.
  for (final c in chips) {
    final t = c.trim().toLowerCase();
    if (t.isNotEmpty) out.add(t);
  }
  for (final t in typed) {
    final n = t.trim().toLowerCase();
    if (n.isNotEmpty) out.add(n);
  }
  return out.toList();
}
