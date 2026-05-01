/// Launches the configured Beats web UI's Insights page in the
/// system browser, optionally pre-filtered. Shared by FlowScreen,
/// CoachScreen, and any future companion surface that wants the
/// same tap-to-open UX.
///
/// Failure (no URL handler, malformed URL) surfaces a SnackBar with
/// the failed URL — silent failure was the previous behavior and
/// made the feature feel broken when beats_web_url pointed
/// somewhere unreachable.
library;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'insights_url.dart';

/// Opens the Insights page in the system browser, filtered if
/// [filter] is given. The caller's [context] must still be mounted
/// when the SnackBar is shown — checked here so caller can fire-and-
/// forget after a row tap without guarding against fast-pop screens.
Future<void> launchInsights(
  BuildContext context,
  String webUrl, [
  InsightsFilter? filter,
]) async {
  final url = buildInsightsUrl(webUrl, filter);
  final uri = Uri.parse(url);
  if (await canLaunchUrl(uri)) {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
    return;
  }
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text('Could not open $url'),
      duration: const Duration(seconds: 4),
    ),
  );
}
