import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../services/flow_summary.dart';
import '../services/launch_insights.dart';
import '../services/token_storage.dart';
import '../theme/beats_refresh.dart';
import '../theme/beats_theme.dart';
import '../theme/grain_overlay.dart';
import '../theme/staggered_entrance.dart';

class CoachScreen extends StatefulWidget {
  final ApiClient client;
  const CoachScreen({super.key, required this.client});

  @override
  State<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends State<CoachScreen> {
  bool _loading = true;
  Map<String, dynamic>? _brief;

  /// Today's flow headline (avg / peak / count) for the small context
  /// strip above the morning brief. Null when /summary is unreachable
  /// or hasn't returned yet — the strip hides cleanly in that case so
  /// the brief stays first-thing-the-user-sees.
  ///
  /// Falls back to yesterday's slice when today is empty (early-
  /// morning case, just opened the laptop). _flowIsToday tracks
  /// which slice we're showing so the strip label can swap.
  int? _flowAvg;
  int? _flowPeak;
  int? _flowCount;
  bool _flowIsToday = true;
  // Loaded once in _refresh so the strip-tap can build a URL without
  // touching SharedPreferences synchronously. Default matches the
  // daemon's [ui] base_url default.
  String _webUrl = 'http://localhost:8080';
  final TokenStorage _storage = TokenStorage();

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final brief = await widget.client.getTodayBrief();
      final webUrl = await _storage.loadWebUrl();

      // Today's flow headline — single round-trip via /summary so
      // we don't paginate windows on the coach screen. Failure is
      // non-fatal; the strip just hides.
      final now = DateTime.now().toUtc();
      final startOfDay = DateTime.utc(now.year, now.month, now.day);
      final flowSummary = await widget.client.getFlowWindowsSummary(
          startOfDay.toIso8601String(), now.toIso8601String());
      var headline = parseFlowSummary(flowSummary);
      var flowIsToday = true;
      // Today's slice is empty — try yesterday so the user opening
      // the app fresh in the morning still gets useful context.
      // Same fallback rule the web FlowHeadline + FlowScreen empty
      // state + `beatsd status` already use.
      if (headline == null) {
        final yEnd = startOfDay;
        final yStart = yEnd.subtract(const Duration(days: 1));
        final ySummary = await widget.client.getFlowWindowsSummary(
            yStart.toIso8601String(), yEnd.toIso8601String());
        headline = parseFlowSummary(ySummary);
        flowIsToday = false;
      }
      final flowAvg = headline?.avg;
      final flowPeak = headline?.peak;
      final flowCount = headline?.count;

      if (mounted) {
        setState(() {
          _brief = brief;
          _flowAvg = flowAvg;
          _flowPeak = flowPeak;
          _flowCount = flowCount;
          _flowIsToday = flowIsToday;
          _webUrl = webUrl;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: SafeArea(
        child: BeatsRefresh(
          onRefresh: _refresh,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
            children: [
              // ── Today's flow headline (above the brief so the user
              //    sees a quick "how today's actually going" before
              //    they read the morning brief). ──
              if (_flowAvg != null && _flowCount != null) ...[
                StaggeredEntrance(child: _buildFlowHeadline()),
                const SizedBox(height: 24),
              ],

              // ── Brief ──
              StaggeredEntrance(
                child: _BriefCard(
                  timestamp: _briefTimestamp(),
                  body: _brief?['body'] as String?,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Compact "TODAY  avg N · peak M · K windows" strip rendered above
  /// the morning brief. Mirrors the FlowScreen stats line in style
  /// (label-then-number, brutalist) so the two screens read as a set.
  Widget _buildFlowHeadline() {
    final labelStyle =
        BeatsType.label.copyWith(color: BeatsColors.textSecondary, letterSpacing: 2);
    final numStyle = BeatsType.label.copyWith(
      color: BeatsColors.textPrimary,
      fontSize: 14,
      letterSpacing: 0,
    );
    // Whole strip is tappable — opens the unfiltered Insights view.
    // Coach screen is a "summary" surface, no specific axis to deep-
    // link by; the whole-strip tap matches FlowScreen's per-axis tap
    // pattern in spirit (tap the flow info → go to Insights). The
    // ↗ glyph is the same affordance cue the FlowScreen rows use.
    return InkWell(
      onTap: _launchInsights,
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        child: Row(
          children: [
            Container(
                width: 3,
                height: 14,
                decoration: BoxDecoration(
                    color: BeatsColors.green, borderRadius: BorderRadius.circular(2))),
            const SizedBox(width: 10),
            Text(_flowIsToday ? 'TODAY' : 'YESTERDAY',
                style: labelStyle.copyWith(color: BeatsColors.green)),
            const SizedBox(width: 16),
            Text('AVG', style: labelStyle),
            const SizedBox(width: 6),
            Text('$_flowAvg', style: numStyle),
            const SizedBox(width: 14),
            Text('PEAK', style: labelStyle),
            const SizedBox(width: 6),
            Text('$_flowPeak', style: numStyle),
            const SizedBox(width: 14),
            Text('${_flowCount}W',
                style: labelStyle.copyWith(color: BeatsColors.textTertiary)),
            const SizedBox(width: 10),
            Text('↗',
                style: labelStyle.copyWith(
                    color: BeatsColors.textTertiary, fontSize: 9)),
          ],
        ),
      ),
    );
  }

  /// Opens the configured Beats web UI's Insights page (unfiltered).
  /// Routes through the shared launchInsights helper so the launch
  /// + SnackBar-on-failure UX stays consistent with FlowScreen.
  Future<void> _launchInsights() => launchInsights(context, _webUrl);

  /// Returns a short local-time string for when today's brief was generated,
  /// e.g. "07:14". Returns null if there's no brief or the timestamp is missing.
  String? _briefTimestamp() {
    final raw = _brief?['created_at'] as String?;
    if (raw == null) return null;
    final ts = DateTime.tryParse(raw);
    if (ts == null) return null;
    final local = ts.toLocal();
    return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }
}

/// Morning brief surface treatment — a softly-warm card with a sunrise
/// gradient bleeding from the top edge and a subtle grain overlay so the
/// surface reads as something hand-made rather than a flat data panel.
///
/// The brief itself is the centerpiece of the Coach tab; the card is what
/// makes the eye land on it. Stays out of the layered widget tree above so
/// the build() method reads as a flat list of sections.
class _BriefCard extends StatelessWidget {
  final String? timestamp;
  final String? body;

  const _BriefCard({this.timestamp, this.body});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: BeatsColors.surfaceAlt,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: BeatsColors.borderAccent.withValues(alpha: 0.6)),
      ),
      // Hard-clip so the sunrise gradient and the grain don't overpaint
      // the rounded corners.
      clipBehavior: Clip.hardEdge,
      child: Stack(
        children: [
          // Grain — drawn first so the gradient and content sit on top.
          const Positioned.fill(child: GrainOverlay(opacity: 0.04)),

          // Sunrise gradient — amber → transparent across the top 56px.
          // Subtle enough to read as warmth-of-the-page rather than
          // decoration; it's the only surface in the app that gets this
          // treatment so the brief feels like the morning's first thing.
          Positioned(
            top: 0, left: 0, right: 0, height: 56,
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      BeatsColors.amber.withValues(alpha: 0.18),
                      BeatsColors.amber.withValues(alpha: 0.0),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // Content
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 22),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 3, height: 14,
                      decoration: BoxDecoration(
                        color: BeatsColors.amber,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Text('MORNING BRIEF',
                      style: BeatsType.label.copyWith(
                        color: BeatsColors.amber,
                        letterSpacing: 2,
                      )),
                    const Spacer(),
                    if (timestamp != null)
                      Text(timestamp!,
                        style: BeatsType.label.copyWith(
                          fontSize: 9,
                          color: BeatsColors.textTertiary,
                          letterSpacing: 1.5,
                        )),
                  ],
                ),
                const SizedBox(height: 16),
                if (body != null && body!.isNotEmpty)
                  Text(
                    body!,
                    style: GoogleFonts.dmSans(
                      fontSize: 15, height: 1.8,
                      color: BeatsColors.textPrimary.withValues(alpha: 0.88),
                      fontWeight: FontWeight.w400,
                    ),
                  )
                else
                  Text(
                    'No brief today. The coach generates one each morning.',
                    style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
