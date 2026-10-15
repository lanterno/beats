import 'dart:async';
import 'dart:math';

import 'api_client.dart';

/// A made-up LifePete server held in memory, for looking around without an
/// account: the store's reviewers, the store's screenshots, and anyone
/// curious before they pair. Every answer is shaped like the real API's and
/// placed relative to the clock, so the day always looks like today: a timer
/// that has run about an hour and a half, the morning's sessions, flow,
/// meetings, a brief, a week of sleep. Starting, stopping and logging work,
/// and last only until the app quits. Nothing leaves the device.
class SampleApi extends ApiClient {
  final DateTime Function() _clock;

  SampleApi({DateTime Function()? clock})
      : _clock = clock ?? DateTime.now,
        super(baseUrl: 'https://sample.lifepete.com') {
    final now = _clock();
    _since = now.toUtc().subtract(const Duration(minutes: 84));
    // The morning before the running session, oldest first.
    final morning = _since.subtract(const Duration(minutes: 16));
    _beats.addAll([
      _beat('spanish', morning.subtract(const Duration(minutes: 135)), morning.subtract(const Duration(minutes: 110))),
      _beat('northwind', morning.subtract(const Duration(minutes: 95)), morning.subtract(const Duration(minutes: 20))),
    ]);
  }

  static const _projects = [
    {'id': 'northwind', 'name': 'Northwind', 'color': '#4F8FD6', 'kind': 'day_job'},
    {'id': 'kite', 'name': 'Studio Kite', 'color': '#E07A5F', 'kind': 'freelance', 'weekly_goal': 5},
    {'id': 'notes', 'name': 'Field Notes', 'color': '#8E7CC3', 'kind': 'side_project', 'weekly_goal': 4},
    {'id': 'spanish', 'name': 'Spanish', 'color': '#2E9C94', 'kind': 'side_project'},
  ];

  /// What each project's past weekdays held, Monday to Friday, in hours.
  static const _pastDays = {
    'northwind': [6.6, 7.1, 6.0, 6.8, 6.3],
    'kite': [1.0, 0, 1.4, 0, 0.8],
    'notes': [0.6, 1.0, 0, 0.9, 0.5],
    'spanish': [0.4, 0.3, 0, 0.5, 0.4],
  };

  /// Where each project's work happens, for the flow windows.
  static const _where = {
    'northwind': ('northwind-api', 'Python', 'com.microsoft.VSCode'),
    'kite': ('studio-kite-web', 'TypeScript', 'com.microsoft.VSCode'),
    'notes': ('field-notes', 'Dart', 'com.microsoft.VSCode'),
    'spanish': (null, null, 'com.apple.Safari'),
  };

  String? _running = 'northwind';
  late DateTime _since;
  final _beats = <Map<String, dynamic>>[];
  String? _feedback;
  var _nextId = 1;

  Map<String, dynamic> _beat(String project, DateTime start, DateTime? end) => {
        'id': 'sample-${_nextId++}',
        'project_id': project,
        'start': start.toUtc().toIso8601String(),
        'end': end?.toUtc().toIso8601String(),
      };

  Map<String, dynamic> _project(String id) => _projects.firstWhere((p) => p['id'] == id);

  DateTime _at(Map<String, dynamic> beat, String key) => DateTime.parse(beat[key] as String);

  /// Every session, the running one ending now.
  List<(String, DateTime, DateTime)> get _sessions {
    final now = _clock().toUtc();
    return [
      for (final b in _beats)
        if (b['end'] != null) (b['project_id'] as String, _at(b, 'start'), _at(b, 'end')),
      if (_running != null) (_running!, _since, now),
    ];
  }

  // ── Pairing and the device ──

  @override
  Future<PairResult> exchangePairCode(String code, {String? deviceName}) async =>
      throw ApiException(400, 'Sample data has nothing to pair with.');

  @override
  Future<void> postHeartbeat() async {}

  @override
  Future<void> postBiometricDay(Map<String, dynamic> data) async {}

  // ── The timer and projects ──

  @override
  Future<Map<String, dynamic>> getTimerStatus() async => _running == null
      ? {'isBeating': false}
      : {'isBeating': true, 'project': _project(_running!), 'since': _since.toIso8601String()};

  @override
  Future<List<Map<String, dynamic>>> getProjects() async => [for (final p in _projects) Map.of(p)];

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime}) async {
    if (_running != null) throw ApiException(409, 'A timer is already running.');
    _running = projectId;
    _since = (startTime == null ? _clock() : DateTime.parse(startTime)).toUtc();
    return {};
  }

  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime}) async {
    final project = _running;
    if (project == null) throw ApiException(409, 'Nothing is running.');
    final beat = _beat(project, _since, stopTime == null ? _clock() : DateTime.parse(stopTime));
    _beats.add(beat);
    _running = null;
    return Map.of(beat);
  }

  @override
  Future<List<Map<String, dynamic>>> getBeatsOn(DateTime utcDay) async {
    bool on(DateTime t) => t.year == utcDay.year && t.month == utcDay.month && t.day == utcDay.day;
    return [
      for (final b in _beats)
        if (on(_at(b, 'start'))) Map.of(b),
      if (_running != null && on(_since)) {'id': 'sample-running', 'project_id': _running, 'start': _since.toIso8601String(), 'end': null},
    ];
  }

  @override
  Future<Map<String, dynamic>> createBeat({
    required String projectId,
    required DateTime start,
    required DateTime end,
  }) async {
    final beat = _beat(projectId, start, end);
    _beats.add(beat);
    return Map.of(beat);
  }

  @override
  Future<Map<String, dynamic>> updateBeat({
    required String id,
    required String projectId,
    required DateTime start,
    DateTime? end,
  }) async {
    if (id == 'sample-running') {
      _running = projectId;
      _since = start.toUtc();
      return {};
    }
    final beat = _beats.firstWhere((b) => b['id'] == id, orElse: () => throw ApiException(404, 'No such session.'));
    if (end == null) {
      // Reopened: the session is running again.
      _beats.remove(beat);
      _running = projectId;
      _since = start.toUtc();
    } else {
      beat
        ..['project_id'] = projectId
        ..['start'] = start.toUtc().toIso8601String()
        ..['end'] = end.toUtc().toIso8601String();
    }
    return {};
  }

  /// One week of a project, Monday first: past weekdays from the sample's
  /// history, today from its sessions.
  @override
  Future<Map<String, dynamic>> getLedger(String projectId, {int weeks = 1, String? timezone}) async {
    final now = _clock();
    final today = now.weekday - 1;
    final past = _pastDays[projectId] ?? const [0, 0, 0, 0, 0];
    final days = [for (var i = 0; i < 7; i++) i < today && i < 5 ? past[i] : 0.0];
    final dayStart = DateTime(now.year, now.month, now.day);
    for (final (p, start, end) in _sessions) {
      if (p == projectId && !start.toLocal().isBefore(dayStart)) {
        days[today] += end.difference(start).inMinutes / 60;
      }
    }
    final worked = days.fold(0.0, (a, b) => a + b);
    final project = _project(projectId);
    final week = {
      'worked': worked,
      'days': days,
      // An 80% contract: 32 hours a week, 6.4 a day.
      if (project['kind'] == 'day_job') 'contract_expected': 32.0,
      if (project['weekly_goal'] != null) ...{'effective_goal': project['weekly_goal'], 'effective_goal_type': 'target'},
    };
    return {
      'weeks': [week],
      if (project['kind'] == 'day_job') 'totals': {'balance': 6.5 + worked - 6.4 * min(today + 1, 5)},
    };
  }

  // ── Flow ──

  /// Five-minute flow windows over [start, end): the day's sessions today,
  /// and a fixed working day on any other.
  List<Map<String, dynamic>> _windows(DateTime start, DateTime end) {
    final now = _clock().toUtc();
    final local = start.toLocal();
    final day = DateTime(local.year, local.month, local.day);
    final isToday = DateTime(now.toLocal().year, now.toLocal().month, now.toLocal().day) == day;
    final spans = isToday
        ? _sessions
        : [
            ('northwind', day.add(const Duration(hours: 9)).toUtc(), day.add(const Duration(hours: 12)).toUtc()),
            ('notes', day.add(const Duration(hours: 13, minutes: 30)).toUtc(), day.add(const Duration(hours: 15)).toUtc()),
            ('northwind', day.add(const Duration(hours: 15, minutes: 15)).toUtc(), day.add(const Duration(hours: 17, minutes: 30)).toUtc()),
          ];
    final out = <Map<String, dynamic>>[];
    for (final (project, from, to) in spans) {
      final (repo, language, bundle) = _where[project]!;
      final length = to.difference(from).inMinutes;
      for (var m = 0; m + 5 <= length; m += 5) {
        final t = from.add(Duration(minutes: m));
        if (t.isBefore(start.toUtc()) || !t.isBefore(end.toUtc())) continue;
        // Settles in over the first half hour, wobbles, and holds.
        final settle = min(m / 30, 1.0);
        final wobble = sin(t.millisecondsSinceEpoch / 600000.0) * 0.08 + sin(m / 7.0) * 0.05;
        final score = (0.32 + 0.52 * settle + wobble).clamp(0.12, 0.96);
        out.add({
          'window_start': t.toIso8601String(),
          'window_end': t.add(const Duration(minutes: 5)).toIso8601String(),
          'flow_score': double.parse(score.toStringAsFixed(2)),
          'editor_repo': repo,
          'editor_language': language,
          'dominant_bundle_id': bundle,
        });
      }
    }
    return out;
  }

  @override
  Future<List<Map<String, dynamic>>> getFlowWindows(String start, String end) async =>
      _windows(DateTime.parse(start), DateTime.parse(end));

  @override
  Future<Map<String, dynamic>?> getFlowWindowsSummary(
    String start,
    String end, {
    String? editorRepo,
    String? editorLanguage,
    String? bundleId,
    String? projectId,
  }) async {
    final w = _windows(DateTime.parse(start), DateTime.parse(end));
    if (w.isEmpty) return {'count': 0};
    final scores = [for (final x in w) x['flow_score'] as double];
    Map<String, dynamic>? top(String field) {
      final counts = <String, int>{};
      for (final x in w) {
        final v = x[field] as String?;
        if (v != null) counts[v] = (counts[v] ?? 0) + 1;
      }
      if (counts.isEmpty) return null;
      final best = counts.entries.reduce((a, b) => b.value > a.value ? b : a);
      return {'key': best.key, 'count': best.value};
    }

    return {
      'count': w.length,
      'avg': scores.reduce((a, b) => a + b) / scores.length,
      'peak': scores.reduce(max),
      'top_repo': top('editor_repo'),
      'top_language': top('editor_language'),
      'top_bundle': top('dominant_bundle_id'),
    };
  }

  @override
  Future<List<Map<String, dynamic>>> getSignalSummaries(String start, String end) async {
    final n = _windows(DateTime.parse(start), DateTime.parse(end)).length;
    if (n == 0) return [];
    return [
      {
        'categories': {
          'coding': (n * 2.9).round(),
          'browser': (n * 0.85).round(),
          'communication': (n * 0.7).round(),
          'design': (n * 0.3).round(),
          'other': (n * 0.25).round(),
        },
      },
    ];
  }

  @override
  Future<List<Map<String, dynamic>>> getPendingSuggestions({DateTime? since, int limit = 20}) async => [];

  @override
  Future<List<Map<String, dynamic>>> getRecentDrift({DateTime? since, int limit = 20}) async => [];

  @override
  Future<List<Map<String, dynamic>>> getHeatmap({int? year}) async => [];

  // ── Calendar ──

  @override
  Future<List<Map<String, dynamic>>> getCalendarEvents(DateTime start, DateTime end) async {
    final now = _clock();
    final day = DateTime(now.year, now.month, now.day);
    Map<String, dynamic> event(String summary, int hour, int minute, int length) {
      final from = day.add(Duration(hours: hour, minutes: minute));
      return {
        'summary': summary,
        'start': from.toUtc().toIso8601String(),
        'end': from.add(Duration(minutes: length)).toUtc().toIso8601String(),
        'all_day': false,
      };
    }

    return [
      event('Standup', 10, 0, 15),
      event('Design review', 13, 0, 60),
      event('1:1 with Sam', 16, 30, 30),
    ];
  }

  // ── The coach ──

  Map<String, dynamic> get _brief {
    final now = _clock();
    final day = DateTime(now.year, now.month, now.day);
    return {
      'date': '${day.year}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}',
      'created_at': day.add(const Duration(hours: 7, minutes: 14)).toUtc().toIso8601String(),
      'feedback': _feedback,
      'body': '# Protect the morning. The afternoon is already spoken for.\n\n'
          'You logged 8h on Northwind yesterday, but it came in nine short windows — none past '
          '25 minutes. Calendar breaks at 10:00 and 11:30 did most of the cutting.\n\n'
          'Today only the design review at 13:00 is fixed. Start Northwind early, keep chat closed '
          'until standup, and you have room for one long block.\n\n'
          'You slept 7h 24m and readiness is 82, so there\'s no reason to go easy.',
    };
  }

  @override
  Future<Map<String, dynamic>?> getTodayBrief({String? timezone}) async => _brief;

  @override
  Future<Map<String, dynamic>> generateBrief({String? timezone}) async => _brief;

  @override
  Future<Map<String, dynamic>> setBriefFeedback(String date, String? rating) async {
    _feedback = rating;
    return _brief;
  }

  @override
  Future<Map<String, dynamic>> getCoachMemory() async => {
        'content': '- Mornings are the best time for deep work.\n'
            '- Studio Kite invoices on the last Friday of the month.\n'
            '- Wants Spanish to happen three times a week, even briefly.\n'
            '- Prefers a short brief over a long one.',
        'updated_at': _clock().subtract(const Duration(days: 2)).toUtc().toIso8601String(),
      };

  @override
  Future<List<Map<String, dynamic>>> getChatHistory({String? conversationId, int limit = 50}) async => [
        {'role': 'user', 'content': 'Why did yesterday feel so choppy?'},
        {
          'role': 'assistant',
          'content': 'Three things cut it up: meetings at 10:00 and 11:30, six trips to Mail, and a switch '
              'to Field Notes at 14:10 that never got going. Your longest window was 25 minutes.',
        },
      ];

  @override
  Stream<Map<String, dynamic>> streamChat(String message, {String? conversationId}) async* {
    const reply = 'This is sample data, so I can only talk about the made-up week you\'re looking at: '
        'Northwind is on pace, Field Notes is most of the way to its goal, and Spanish '
        'has been quiet for a few days. Pair your own account and I\'ll answer from your real time.';
    for (final word in reply.split(' ')) {
      await Future<void>.delayed(const Duration(milliseconds: 25));
      yield {'type': 'text', 'text': '$word '};
    }
    yield {'type': 'done', 'conversation_id': 'sample'};
  }

  // ── The body ──

  @override
  Future<List<Map<String, dynamic>>> getBiometrics(String start, String end) async {
    final from = DateTime.parse(start), to = DateTime.parse(end);
    const sleep = [366, 408, 450, 354, 420, 468, 444];
    const hrv = [41, 39, 45, 38, 44, 46, 48];
    const rhr = [59, 60, 57, 61, 58, 57, 56];
    const readiness = [71, 68, 78, 64, 75, 80, 82];
    const steps = [8200, 6400, 9100, 4300, 7600, 10200, 1840];
    final today = DateTime(_clock().year, _clock().month, _clock().day);
    final out = <Map<String, dynamic>>[];
    for (var d = from; !d.isAfter(to); d = DateTime(d.year, d.month, d.day + 1)) {
      final back = today.difference(d).inDays; // 0 today .. 6
      if (back < 0 || back > 6) continue;
      final i = 6 - back;
      out.add({
        'date': '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}',
        'source': 'oura',
        'sleep_minutes': sleep[i],
        'sleep_efficiency': 91,
        'hrv_ms': hrv[i],
        'resting_hr_bpm': rhr[i],
        'readiness_score': readiness[i],
        'steps': steps[i],
        'created_at': d.add(const Duration(hours: 7, minutes: 2)).toUtc().toIso8601String(),
      });
    }
    return out;
  }

  @override
  Future<Map<String, dynamic>> getOuraStatus() async => {'connected': true};

  @override
  Future<Map<String, dynamic>> getFitbitStatus() async => {'connected': false};

  @override
  Future<void> connectOura(String pat) async => throw ApiException(400, 'Pair your own account to connect Oura.');

  @override
  Future<void> disconnectOura() async => throw ApiException(400, 'Sample data stays connected.');

  @override
  Future<void> disconnectFitbit() async {}

  @override
  Future<Map<String, dynamic>> getFitbitAuthUrl() async =>
      throw ApiException(400, 'Pair your own account to connect Fitbit.');
}
