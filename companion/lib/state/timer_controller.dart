import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

import '../services/api_client.dart';
import '../services/recent_projects.dart';
import '../ui/kit.dart';

/// One project, as every screen needs it.
class Project {
  final String id;
  final String name;
  final Color color;

  /// `day_job`, `freelance` or `side_project`.
  final String kind;
  final bool archived;
  final double? weeklyGoal;

  /// The organisation that owns the project, when it is not the person
  /// tracking on it (docs/organisations.md): its name marks the project
  /// wherever the kind is shown. Tracking on it is no different.
  final String? organisationName;

  const Project({
    required this.id,
    required this.name,
    required this.color,
    required this.kind,
    this.archived = false,
    this.weeklyGoal,
    this.organisationName,
  });

  factory Project.fromJson(Map<String, dynamic> j) => Project(
        id: j['id'] as String? ?? '',
        name: j['name'] as String? ?? 'Untitled',
        color: projectColor(j['color'] as String?),
        kind: j['kind'] as String? ?? 'side_project',
        archived: j['archived'] == true,
        weeklyGoal: (j['weekly_goal'] as num?)?.toDouble(),
        organisationName: (j['organisation'] as Map?)?['name'] as String?,
      );

  /// "Day job", or on an organisation's project "Day job · Acme" — the one
  /// line every list and the menu bar put under a project's name.
  String get kindLabel {
    final base = switch (kind) {
      'day_job' => 'Day job',
      'freelance' => 'Freelance',
      _ => 'Side project',
    };
    final org = organisationName;
    return org == null || org.isEmpty ? base : '$base · $org';
  }
}

/// The session a stop just closed, kept for a minute so it can be undone.
class StoppedSession {
  final Map<String, dynamic> beat;
  final Project project;
  final Duration length;
  final DateTime at;
  const StoppedSession(this.beat, this.project, this.length, this.at);
}

/// The timer, shared by every surface that shows or drives it: Today, the
/// sidebar, the palette, focus mode. Polls the API every 15 seconds (another
/// device, the web app or the daemon may have started or stopped it) and
/// ticks [now] every second while a timer runs.
class TimerController extends ChangeNotifier {
  final ApiClient client;
  final RecentProjects _recents;

  TimerController(this.client, {RecentProjects? recents}) : _recents = recents ?? RecentProjects();

  List<Project> projects = const [];
  List<String> recentIds = const [];
  bool loaded = false;
  Object? error;

  Project? current;
  DateTime? since;
  StoppedSession? lastStopped;

  /// Ticks every second while a timer runs; listen to it for the clock
  /// rather than to the controller, which only notifies when state changes.
  final ValueNotifier<DateTime> now = ValueNotifier(DateTime.now());

  Timer? _poll;
  Timer? _tick;

  bool get running => current != null && since != null;
  Duration get elapsed => running ? now.value.toUtc().difference(since!) : Duration.zero;

  /// Live projects, the recently used first.
  List<Project> get recentFirst {
    final live = projects.where((p) => !p.archived).toList();
    int rank(Project p) {
      final i = recentIds.indexOf(p.id);
      return i < 0 ? recentIds.length : i;
    }

    live.sort((a, b) => rank(a).compareTo(rank(b)));
    return live;
  }

  Project? projectById(String? id) => projects.where((p) => p.id == id).firstOrNull;

  void start() {
    unawaited(refresh());
    unawaited(_loadRecents());
    _poll = Timer.periodic(const Duration(seconds: 15), (_) => refresh());
  }

  Future<void> _loadRecents() async {
    recentIds = await _recents.load();
    notifyListeners();
  }

  Future<void> refresh() async {
    try {
      final results = await Future.wait([client.getTimerStatus(), client.getProjects()]);
      final status = results[0] as Map<String, dynamic>;
      projects = (results[1] as List<Map<String, dynamic>>).map(Project.fromJson).toList();
      final beating = status['isBeating'] == true && status['since'] != null;
      if (beating) {
        final p = status['project'] as Map<String, dynamic>?;
        current = projectById(p?['id'] as String?) ?? (p != null ? Project.fromJson(p) : null);
        since = DateTime.tryParse(status['since'] as String)?.toUtc();
      } else {
        current = null;
        since = null;
      }
      error = null;
    } catch (e) {
      error = e;
    }
    loaded = true;
    _syncTicker();
    notifyListeners();
  }

  void _syncTicker() {
    if (running && _tick == null) {
      _tick = Timer.periodic(const Duration(seconds: 1), (_) => now.value = DateTime.now());
    } else if (!running) {
      _tick?.cancel();
      _tick = null;
    }
    now.value = DateTime.now();
  }

  /// Starts [project] at [at] (default now). Throws on failure, leaving the
  /// state as the server reports it.
  Future<void> startProject(Project project, {DateTime? at}) async {
    final start = (at ?? DateTime.now()).toUtc();
    current = project;
    since = start;
    lastStopped = null;
    _syncTicker();
    notifyListeners();
    try {
      await client.startTimer(project.id, startTime: start.toIso8601String());
      await _recents.markUsed(project.id);
      recentIds = await _recents.load();
    } finally {
      await refresh();
    }
  }

  /// Stops the running timer at [at] (default now) and keeps the closed
  /// session in [lastStopped] for [undoStop].
  Future<StoppedSession?> stop({DateTime? at}) async {
    final project = current;
    final started = since;
    if (project == null || started == null) return null;
    final end = (at ?? DateTime.now()).toUtc();
    current = null;
    since = null;
    _syncTicker();
    notifyListeners();
    try {
      final beat = await client.stopTimer(stopTime: end.toIso8601String());
      lastStopped = StoppedSession(beat, project, end.difference(started), DateTime.now());
      return lastStopped;
    } finally {
      await refresh();
    }
  }

  /// Stops whatever runs at [at] and starts [project] from the same moment,
  /// so no minute is lost or counted twice.
  Future<void> switchTo(Project project, {DateTime? at}) async {
    final t = (at ?? DateTime.now()).toUtc();
    if (running) await stop(at: t);
    await startProject(project, at: t);
  }

  /// Reopens the session the last stop closed, as if it had never stopped.
  Future<void> undoStop() async {
    final s = lastStopped;
    if (s == null || running) return;
    lastStopped = null;
    notifyListeners();
    try {
      await client.updateBeat(
        id: s.beat['id'] as String,
        projectId: s.beat['project_id'] as String,
        start: DateTime.parse(s.beat['start'] as String),
      );
    } finally {
      await refresh();
    }
  }

  /// Moves the running timer's start to [start] ("I started earlier").
  Future<void> moveStart(DateTime start) async {
    final project = current;
    final started = since;
    if (project == null || started == null) return;
    // The API files a session under the UTC day it started on.
    final beats = await client.getBeatsOn(started.toUtc());
    final active = beats.where((b) => b['end'] == null && b['project_id'] == project.id).firstOrNull;
    if (active == null) throw StateError('The running session was not found');
    await client.updateBeat(id: active['id'] as String, projectId: project.id, start: start);
    await refresh();
  }

  void forgetStopped() {
    if (lastStopped == null) return;
    lastStopped = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _tick?.cancel();
    now.dispose();
    super.dispose();
  }
}
