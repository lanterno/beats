import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

import '../services/api_client.dart';
import 'timer_controller.dart';

/// One project's current week, read off its ledger.
class ProjectWeek {
  final Project project;

  /// Hours worked this week, and per day Monday..Sunday.
  final double worked;
  final List<double> days;

  /// The hours the week asks for: a day job's contract expectation
  /// (holidays and absences taken out), else a target goal. Null when the
  /// project has neither, or its goal is a cap.
  final double? target;

  /// A day job's balance as of today, in hours; null otherwise.
  final double? balance;

  const ProjectWeek({
    required this.project,
    required this.worked,
    required this.days,
    this.target,
    this.balance,
  });

  /// Parses the newest week of a `/ledger` response, or null when it has none.
  static ProjectWeek? fromLedger(Project project, Map<String, dynamic> ledger) {
    final weeks = ledger['weeks'] as List?;
    if (weeks == null || weeks.isEmpty) return null;
    final w = weeks.first as Map<String, dynamic>;
    final days = ((w['days'] as List?) ?? const [])
        .map((d) => (d as num).toDouble())
        .toList();
    final expected = (w['contract_expected'] as num?)?.toDouble();
    final goal = (w['effective_goal'] as num?)?.toDouble();
    final isCap = w['effective_goal_type'] == 'cap';
    final totals = ledger['totals'] as Map<String, dynamic>?;
    return ProjectWeek(
      project: project,
      worked: (w['worked'] as num?)?.toDouble() ?? 0,
      days: days.length == 7 ? days : List.filled(7, 0),
      target: expected ?? (isCap ? null : goal),
      balance: (totals?['balance'] as num?)?.toDouble(),
    );
  }
}

/// The week across projects, for the sidebar's hours, Today's week card and
/// ring, and the Coach's "where your week stands". Reloads every five
/// minutes and whenever the timer starts, stops or switches.
class WeekController extends ChangeNotifier {
  final ApiClient client;
  final TimerController timer;
  WeekController(this.client, this.timer);

  List<ProjectWeek> weeks = const [];
  DateTime? loadedAt;
  String? _tz;
  Timer? _poll;
  String _lastTimerKey = '';

  void start() {
    unawaited(refresh());
    _poll = Timer.periodic(const Duration(minutes: 5), (_) => refresh());
    timer.addListener(_onTimer);
  }

  void _onTimer() {
    final key = '${timer.current?.id}@${timer.since}';
    if (key == _lastTimerKey) return;
    _lastTimerKey = key;
    unawaited(refresh());
  }

  Future<void> refresh() async {
    try {
      _tz ??= (await FlutterTimezone.getLocalTimezone()).identifier;
    } catch (_) {
      _tz = null; // The API buckets in UTC without one.
    }
    final live = timer.projects.where((p) => !p.archived).toList();
    final results = await Future.wait(live.map((p) async {
      try {
        return ProjectWeek.fromLedger(p, await client.getLedger(p.id, timezone: _tz));
      } catch (_) {
        // A failed reload (offline, rate-limited) keeps the last good week
        // rather than blanking the project out of every screen.
        return weekOf(p.id);
      }
    }));
    weeks = results.whereType<ProjectWeek>().toList()
      ..sort((a, b) => b.worked.compareTo(a.worked));
    loadedAt = DateTime.now();
    notifyListeners();
  }

  ProjectWeek? weekOf(String projectId) =>
      weeks.where((w) => w.project.id == projectId).firstOrNull;

  /// The project the week card is about: the day job when there is one,
  /// else the project with the largest target.
  ProjectWeek? get anchor {
    final dayJob = weeks.where((w) => w.project.kind == 'day_job' && w.target != null).firstOrNull;
    if (dayJob != null) return dayJob;
    final withTarget = weeks.where((w) => w.target != null).toList()
      ..sort((a, b) => b.target!.compareTo(a.target!));
    return withTarget.firstOrNull;
  }

  /// Minutes tracked today across projects, counting the running timer up
  /// to [now] rather than to the last reload.
  int todayMinutes(DateTime now) {
    final i = now.weekday - 1;
    var hours = 0.0;
    for (final w in weeks) {
      hours += w.days[i];
    }
    var minutes = (hours * 60).round();
    final since = timer.since;
    if (timer.running && since != null) {
      final from = loadedAt != null && loadedAt!.toUtc().isAfter(since) ? loadedAt!.toUtc() : since;
      final extra = now.toUtc().difference(from).inMinutes;
      if (extra > 0) minutes += extra;
    }
    return minutes;
  }

  /// Today's share of the week's targets: each target spread over Monday to
  /// Friday. Null on a weekend, or when no project has a target.
  int? dailyTargetMinutes(DateTime now) {
    if (now.weekday > 5) return null;
    final targets = weeks.map((w) => w.target).whereType<double>();
    if (targets.isEmpty) return null;
    return (targets.fold(0.0, (a, b) => a + b) / 5 * 60).round();
  }

  @override
  void dispose() {
    _poll?.cancel();
    timer.removeListener(_onTimer);
    super.dispose();
  }
}
