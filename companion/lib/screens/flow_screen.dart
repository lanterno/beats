import 'dart:async';
import 'dart:io';

import 'package:material_ui/material_ui.dart';

import '../brand.dart';
import '../services/api_client.dart';
import '../services/bundle_label.dart';
import '../services/date_keys.dart';
import '../services/flow_story.dart';
import '../services/flow_summary.dart';
import '../services/insights_url.dart';
import '../services/launch_insights.dart';
import '../services/time_format.dart';
import '../services/token_storage.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';

const _categoryColors = {
  'coding': Color(0xFF4F8FD6),
  'browser': Color(0xFF2E9C94),
  'communication': Color(0xFF8E7CC3),
  'design': Color(0xFFE07A5F),
  'writing': Color(0xFFF2B233),
  'social': Color(0xFFFB923C),
  'other': Color(0xFFA7B4BD),
};

Color _categoryColor(String c) => _categoryColors[c] ?? _categoryColors['other']!;

String _capitalised(String s) => s.isEmpty ? s : '${s[0].toUpperCase()}${s.substring(1)}';

enum _Day { today, yesterday }

/// One day of the slice the screen shows, loaded together.
class _DayData {
  final List<FlowSample> samples;
  final Map<String, int> categories;
  final FlowHeadline? headline;
  const _DayData(this.samples, this.categories, this.headline);
}

/// Flow: how focused the day was, in a sentence, a chart of five-minute
/// bars to pick through, the repo, language and app it happened in, and
/// where attention went.
class FlowScreen extends StatefulWidget {
  final ApiClient client;
  const FlowScreen({super.key, required this.client});

  @override
  State<FlowScreen> createState() => _FlowScreenState();
}

class _FlowScreenState extends State<FlowScreen> {
  _Day _day = _Day.today;
  final _data = <_Day, _DayData>{};
  FlowHeadline? _yesterdaySummary;
  bool _loading = true;
  /// The web app, for the Insights links; null hides them.
  String? _webUrl;
  int? _selected;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(minutes: 1), (_) {
      if (_day == _Day.today) _load(quiet: true);
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  (DateTime, DateTime) _range(_Day day) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return day == _Day.today ? (today, now) : (addDays(today, -1), today);
  }

  Future<void> _load({bool quiet = false}) async {
    if (!quiet) setState(() => _loading = true);
    final day = _day;
    final (from, to) = _range(day);
    final start = from.toUtc().toIso8601String();
    final end = to.toUtc().toIso8601String();
    try {
      final webUrl = await TokenStorage().loadWebUrl();
      final results = await Future.wait([
        widget.client.getFlowWindows(start, end),
        widget.client.getSignalSummaries(start, end).catchError((_) => <Map<String, dynamic>>[]),
        widget.client.getFlowWindowsSummary(start, end),
      ]);
      final categories = <String, int>{};
      for (final s in results[1] as List<Map<String, dynamic>>) {
        final c = s['categories'] as Map<String, dynamic>? ?? const {};
        for (final e in c.entries) {
          if (e.value is num) categories[e.key] = (categories[e.key] ?? 0) + (e.value as num).toInt();
        }
      }
      FlowHeadline? yesterday = _yesterdaySummary;
      if (day == _Day.today && yesterday == null) {
        final (yFrom, yTo) = _range(_Day.yesterday);
        yesterday = parseFlowSummary(await widget.client
            .getFlowWindowsSummary(yFrom.toUtc().toIso8601String(), yTo.toUtc().toIso8601String()));
      }
      if (!mounted || day != _day) return;
      final data = _DayData(
        FlowSample.listFrom(results[0] as List<Map<String, dynamic>>),
        categories,
        parseFlowSummary(results[2] as Map<String, dynamic>?),
      );
      setState(() {
        _webUrl = webUrl;
        _data[day] = data;
        _yesterdaySummary = yesterday;
        _loading = false;
        if (!quiet || _selected == null) _selected = _defaultSelection(data.samples);
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// The bar holding the day's peak, so the detail line starts on it.
  int? _defaultSelection(List<FlowSample> samples) {
    final bars = flowBars(samples);
    final peak = peakSample(samples);
    if (bars.isEmpty || peak == null) return null;
    final i = bars.indexWhere((b) => !peak.start.isBefore(b.start) && peak.start.isBefore(b.end));
    return i < 0 ? null : i;
  }

  void _switchDay(_Day day) {
    if (day == _day) return;
    setState(() {
      _day = day;
      _selected = _data[day] == null ? null : _defaultSelection(_data[day]!.samples);
    });
    _load(quiet: _data[day] != null);
  }

  @override
  Widget build(BuildContext context) {
    final data = _data[_day];
    return ListView(
      padding: pagePadding(context),
      children: [
        _Column(children: [
          _header(context),
          const SizedBox(height: 18),
          if (data == null && _loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 80),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (data == null || data.samples.isEmpty)
            _empty(context)
          else ...[
            _headlinePanel(context, data),
            const SizedBox(height: 18),
            _chart(context, data),
            const SizedBox(height: 18),
            _tiles(context, data),
            if (categoryShares(data.categories).isNotEmpty) ...[
              const SizedBox(height: 18),
              _attention(context, data),
            ],
          ],
        ]),
      ],
    );
  }

  Widget _header(BuildContext context) {
    final p = context.sky;
    return Wrap(
      spacing: 16,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      alignment: WrapAlignment.spaceBetween,
      children: [
        Semantics(header: true, child: Text('Flow', style: SkyType.display(isCompact(context) ? 30 : 34))),
        Wrap(spacing: 12, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          SegmentedPills<_Day>(
            options: const [(_Day.today, 'Today'), (_Day.yesterday, 'Yesterday')],
            value: _day,
            onChanged: _switchDay,
          ),
          if (_webUrl != null) Material(
            color: p.panel,
            shape: const StadiumBorder(),
            child: InkWell(
              customBorder: const StadiumBorder(),
              onTap: () => launchInsights(context, _webUrl!),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Text('Insights on the web',
                      style: SkyType.body(14, weight: FontWeight.w700).copyWith(color: p.sunInk)),
                  const SizedBox(width: 6),
                  Icon(Icons.north_east_rounded, size: 15, color: p.sunInk),
                ]),
              ),
            ),
          ),
        ]),
      ],
    );
  }

  Widget _empty(BuildContext context) {
    final y = _yesterdaySummary;
    final today = _day == _Day.today;
    return Panel(
      child: EmptyNote(
        icon: Icons.air_rounded,
        title: today ? 'No flow yet today' : 'No flow yesterday',
        body: [
          'Flow comes from beatsd, the $appName daemon on ${Platform.isMacOS ? 'this Mac' : 'your computer'}: '
              'it notices which app is in '
              'front and how steadily you work, minute by minute. Pair it and run it, and the day fills in here.',
          if (today && y != null) 'Yesterday averaged ${y.avg}, peaking at ${y.peak}.',
        ].join('\n\n'),
      ),
    );
  }

  Widget _headlinePanel(BuildContext context, _DayData data) {
    final p = context.sky;
    final avg = ((averageScore(data.samples) ?? 0) * 100).round();
    final peak = peakSample(data.samples);
    final (tint, ink) = avg >= 70
        ? (p.leaf, p.leafInk)
        : avg >= 45
            ? (p.sun, p.sunInk)
            : (p.persimmon, p.persimmonInk);
    final sub = _day == _Day.today ? comparedWithYesterday(avg, _yesterdaySummary?.avg) : null;
    final active = data.samples.fold(Duration.zero, (a, s) => a + s.end.difference(s.start));

    final circle = Container(
      width: 104,
      height: 104,
      decoration: BoxDecoration(color: tint.withValues(alpha: 0.16), shape: BoxShape.circle),
      child: Semantics(
        label: 'Average flow $avg out of 100',
        excludeSemantics: true,
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text('$avg', style: SkyType.figure(40).copyWith(color: ink)),
          const SizedBox(height: 4),
          Text('average', style: SkyType.body(12).copyWith(color: ink)),
        ]),
      ),
    );
    final story = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(flowHeadline(data.samples, today: _day == _Day.today),
          style: SkyType.display(22, weight: FontWeight.w700).copyWith(height: 1.4)),
      if (sub != null) ...[
        const SizedBox(height: 8),
        Text(sub, style: SkyType.body(14).copyWith(color: p.inkOnSky)),
      ],
    ]);
    Widget fact(String k, String v) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            SizedBox(width: 64, child: Text(k, style: SkyType.body(14).copyWith(color: p.inkMuted))),
            Text(v, style: SkyType.figure(14, weight: FontWeight.w700)),
          ]),
        );
    final facts = Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      if (peak != null) fact('Peak', '${(peak.score * 100).round()} at ${formatTimeOfDay(peak.start)}'),
      fact('In flow', formatDuration(timeInFlow(data.samples))),
      fact('Active', formatDuration(active)),
    ]);

    return Panel(
      raised: true,
      padding: const EdgeInsets.fromLTRB(30, 26, 30, 26),
      child: LayoutBuilder(builder: (context, box) {
        if (box.maxWidth < 640) {
          return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [circle, const SizedBox(width: 20), Expanded(child: facts)]),
            const SizedBox(height: 18),
            story,
          ]);
        }
        return Row(children: [
          circle,
          const SizedBox(width: 28),
          Expanded(child: story),
          const SizedBox(width: 28),
          facts,
        ]);
      }),
    );
  }

  Color _barColor(SkyPalette p, double? score) {
    if (score == null) return p.wash;
    if (score >= flowLine) return p.leaf;
    if (score >= 0.45) return p.hills[1];
    return p.hills[0];
  }

  Widget _chart(BuildContext context, _DayData data) {
    final p = context.sky;
    final bars = flowBars(data.samples);
    final selected = _selected != null && _selected! < bars.length ? bars[_selected!] : null;
    const height = 170.0;
    final hours = bars.isEmpty ? 0 : bars.length ~/ 12;
    final labelEvery = hours > 12 ? 2 : 1;

    void selectAt(double dx, double width) {
      if (bars.isEmpty || width <= 0) return;
      final i = (dx / width * bars.length).floor().clamp(0, bars.length - 1);
      if (i != _selected) setState(() => _selected = i);
    }

    return Panel(
      padding: const EdgeInsets.fromLTRB(26, 22, 26, 22),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const PanelHeading('Through the day',
            subtitle: 'Each bar is five minutes. Pick one to see what you were doing.'),
        const SizedBox(height: 16),
        LayoutBuilder(builder: (context, box) {
          final width = box.maxWidth;
          return GestureDetector(
            onHorizontalDragUpdate: (d) => selectAt(d.localPosition.dx, width),
            child: SizedBox(
              height: height,
              child: Stack(clipBehavior: Clip.none, children: [
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: height * flowLine,
                  child: Container(height: 1, color: p.ink.withValues(alpha: 0.16)),
                ),
                Positioned(
                  right: 0,
                  bottom: height * flowLine + 4,
                  child: Text('flow line, 70', style: SkyType.body(11).copyWith(color: p.inkMuted)),
                ),
                Positioned.fill(
                  child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    for (var i = 0; i < bars.length; i++)
                      Expanded(
                        child: Semantics(
                          button: true,
                          selected: i == _selected,
                          label: bars[i].score == null
                              ? '${formatTimeOfDay(bars[i].start)}, no activity'
                              : '${formatTimeOfDay(bars[i].start)}, flow ${(bars[i].score! * 100).round()}',
                          onTap: () => setState(() => _selected = i),
                          child: MouseRegion(
                            cursor: SystemMouseCursors.click,
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: () => setState(() => _selected = i),
                              child: Align(
                                alignment: Alignment.bottomCenter,
                                child: Container(
                                  margin: EdgeInsets.symmetric(horizontal: bars.length > 120 ? 0.5 : 1),
                                  height: bars[i].score == null
                                      ? 4
                                      : (bars[i].score! * (height - 8)).clamp(4, height - 8).toDouble(),
                                  decoration: BoxDecoration(
                                    color: _barColor(p, bars[i].score),
                                    borderRadius: const BorderRadius.vertical(
                                        top: Radius.circular(4), bottom: Radius.circular(1)),
                                    border: i == _selected ? Border.all(color: p.ink, width: 2) : null,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                  ]),
                ),
              ]),
            ),
          );
        }),
        Container(height: 1, color: p.hairline),
        const SizedBox(height: 8),
        Row(children: [
          for (var h = 0; h < hours; h++)
            Expanded(
              child: h % labelEvery == 0
                  ? Text(formatTimeOfDay(bars[h * 12].start),
                      style: SkyType.figure(11, weight: FontWeight.w500).copyWith(color: p.inkMuted))
                  : const SizedBox.shrink(),
            ),
        ]),
        const SizedBox(height: 14),
        if (selected != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            decoration: BoxDecoration(color: p.wash, borderRadius: BorderRadius.circular(18)),
            child: Wrap(spacing: 16, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              Text('${formatTimeOfDay(selected.start)}–${formatTimeOfDay(selected.end)}',
                  style: SkyType.figure(15)),
              Chip2(
                selected.score == null ? 'No activity' : 'Flow ${(selected.score! * 100).round()}',
                bold: true,
                background: p.panel,
              ),
              Text(_whatYouDid(selected), style: SkyType.body(14)),
            ]),
          ),
      ]),
    );
  }

  String _whatYouDid(FlowBar bar) {
    if (bar.score == null) return 'Away, or nothing the daemon could see.';
    final parts = [
      ?bar.repo,
      ?bar.language,
      if (bar.bundle != null) shortBundleLabel(bar.bundle!),
    ];
    return parts.isEmpty ? 'No editor or app recorded.' : parts.join(' · ');
  }

  Widget _tiles(BuildContext context, _DayData data) {
    final h = data.headline;
    final byRepo = timeInFlowBy(data.samples, (s) => s.repo);
    final byLanguage = timeInFlowBy(data.samples, (s) => s.language);
    final byBundle = timeInFlowBy(data.samples, (s) => s.bundle);
    String note(Map<String, Duration> by, String? key) {
      final d = key == null ? null : by[key];
      return d == null || d == Duration.zero ? 'Open in Insights' : '${formatDuration(d)} in flow';
    }

    final tiles = [
      _Tile(
        label: 'Best repo',
        value: h?.topRepo,
        note: note(byRepo, h?.topRepo),
        onTap: h?.topRepo == null || _webUrl == null
            ? null
            : () => launchInsights(context, _webUrl!, InsightsFilter(repo: h!.topRepo)),
      ),
      _Tile(
        label: 'Best language',
        value: h?.topLanguage,
        note: note(byLanguage, h?.topLanguage),
        onTap: h?.topLanguage == null || _webUrl == null
            ? null
            : () => launchInsights(context, _webUrl!, InsightsFilter(language: h!.topLanguage)),
      ),
      _Tile(
        label: 'Best app',
        value: h?.topBundle == null ? null : shortBundleLabel(h!.topBundle!),
        note: note(byBundle, h?.topBundle),
        onTap: h?.topBundle == null || _webUrl == null
            ? null
            : () => launchInsights(context, _webUrl!, InsightsFilter(bundle: h!.topBundle)),
      ),
    ];
    return LayoutBuilder(builder: (context, box) {
      final cols = box.maxWidth >= 700 ? 3 : (box.maxWidth >= 460 ? 2 : 1);
      const gap = 18.0;
      final width = (box.maxWidth - gap * (cols - 1)) / cols;
      return Wrap(spacing: gap, runSpacing: gap, children: [
        for (final t in tiles) SizedBox(width: width, child: t),
      ]);
    });
  }

  Widget _attention(BuildContext context, _DayData data) {
    final p = context.sky;
    final shares = categoryShares(data.categories);
    return Panel(
      padding: const EdgeInsets.fromLTRB(26, 22, 26, 22),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const PanelHeading('Where your attention went'),
        const SizedBox(height: 14),
        Semantics(
          label: shares.map((s) => '${_capitalised(s.$1)} ${s.$2}%').join(', '),
          excludeSemantics: true,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: SizedBox(
              height: 18,
              child: Row(children: [
                for (final (i, (name, pct)) in shares.indexed) ...[
                  if (i > 0) const SizedBox(width: 3),
                  Expanded(flex: pct, child: ColoredBox(color: _categoryColor(name))),
                ],
              ]),
            ),
          ),
        ),
        const SizedBox(height: 14),
        Wrap(spacing: 22, runSpacing: 10, children: [
          for (final (name, pct) in shares)
            Row(mainAxisSize: MainAxisSize.min, children: [
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(color: _categoryColor(name), borderRadius: BorderRadius.circular(3)),
              ),
              const SizedBox(width: 8),
              Text(_capitalised(name), style: SkyType.body(14)),
              const SizedBox(width: 6),
              Text('$pct%', style: SkyType.figure(14, weight: FontWeight.w700).copyWith(color: p.ink)),
            ]),
        ]),
      ]),
    );
  }
}

class _Tile extends StatelessWidget {
  final String label;
  final String? value;
  final String note;
  final VoidCallback? onTap;
  const _Tile({required this.label, required this.value, required this.note, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Material(
      color: p.panel,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(24),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 20),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: SkyType.body(13).copyWith(color: p.inkMuted)),
            const SizedBox(height: 6),
            Text(value ?? '—',
                maxLines: 1, overflow: TextOverflow.ellipsis, style: SkyType.display(20)),
            const SizedBox(height: 6),
            Row(children: [
              Flexible(child: Text(note, style: SkyType.body(13).copyWith(color: p.inkOnSky))),
              if (onTap != null) ...[
                const SizedBox(width: 4),
                Icon(Icons.north_east_rounded, size: 13, color: p.inkOnSky),
              ],
            ]),
          ]),
        ),
      ),
    );
  }
}

/// Keeps a screen's content to a readable width on a wide window.
class _Column extends StatelessWidget {
  final List<Widget> children;
  const _Column({required this.children});

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1040),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
        ),
      );
}
