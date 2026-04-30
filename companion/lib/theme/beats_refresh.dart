import 'package:flutter/material.dart';

import 'beats_theme.dart';

/// Pull-to-refresh wrapper with the project's brutalist styling: a smaller,
/// thinner amber indicator on a `surface`-tinted backdrop, displaced closer
/// to the top edge so it doesn't push too far into the content.
///
/// Drop-in replacement for `RefreshIndicator(child: ..., onRefresh: ...)`
/// at every call site — same parameter shape, same notification semantics.
class BeatsRefresh extends StatelessWidget {
  final Widget child;
  final Future<void> Function() onRefresh;

  const BeatsRefresh({
    super.key,
    required this.child,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: onRefresh,
      color: BeatsColors.amber,
      backgroundColor: BeatsColors.surface,
      strokeWidth: 2,
      displacement: 28,
      edgeOffset: 0,
      child: child,
    );
  }
}
