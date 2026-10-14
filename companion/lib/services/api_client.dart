import 'dart:convert';
import 'package:http/http.dart' as http;

class PairResult {
  final String deviceToken;
  final String deviceId;
  PairResult({required this.deviceToken, required this.deviceId});
}

class ApiClient {
  final String baseUrl;
  String? deviceToken;

  ApiClient({required this.baseUrl, this.deviceToken});

  Map<String, String> get _headers {
    final h = {'Content-Type': 'application/json'};
    if (deviceToken != null) h['Authorization'] = 'Bearer $deviceToken';
    return h;
  }

  Future<PairResult> exchangePairCode(String code, {String? deviceName}) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/device/pair/exchange'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'code': code,
        // ignore: use_null_aware_elements
        if (deviceName != null) 'device_name': deviceName,
      }),
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Pairing failed');
    }
    final data = jsonDecode(resp.body);
    return PairResult(
      deviceToken: data['device_token'],
      deviceId: data['device_id'],
    );
  }

  Future<void> postHeartbeat() async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/device/heartbeat'),
      headers: _headers,
      body: '{}',
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Heartbeat failed');
    }
  }

  Future<void> postBiometricDay(Map<String, dynamic> data) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/biometrics/daily'),
      headers: _headers,
      body: jsonEncode(data),
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Biometric push failed');
    }
  }

  Future<Map<String, dynamic>> getFitbitAuthUrl() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/fitbit/auth-url'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Failed to get Fitbit auth URL');
    }
    return jsonDecode(resp.body);
  }

  Future<Map<String, dynamic>> getFitbitStatus() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/fitbit/status'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Failed to get Fitbit status');
    }
    return jsonDecode(resp.body);
  }

  Future<Map<String, dynamic>> getOuraStatus() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/oura/status'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Failed to get Oura status');
    }
    return jsonDecode(resp.body);
  }

  Future<void> connectOura(String pat) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/oura/connect'),
      headers: _headers,
      body: jsonEncode({'access_token': pat}),
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Oura connection failed');
    }
  }

  Future<void> disconnectOura() async {
    final resp = await http.delete(
      Uri.parse('$baseUrl/api/oura/disconnect'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Oura disconnect failed');
    }
  }

  Future<void> disconnectFitbit() async {
    final resp = await http.delete(
      Uri.parse('$baseUrl/api/fitbit/disconnect'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Fitbit disconnect failed');
    }
  }

  // ---- Timer ----

  Future<Map<String, dynamic>> getTimerStatus() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/timer/status'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Timer status failed');
    }
    return jsonDecode(resp.body);
  }

  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime}) async {
    final time = startTime ?? DateTime.now().toUtc().toIso8601String();
    final resp = await http.post(
      Uri.parse('$baseUrl/api/projects/$projectId/start'),
      headers: _headers,
      body: jsonEncode({'time': time}),
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Start timer failed');
    }
    return jsonDecode(resp.body);
  }

  Future<Map<String, dynamic>> stopTimer({String? stopTime}) async {
    final time = stopTime ?? DateTime.now().toUtc().toIso8601String();
    final resp = await http.post(
      Uri.parse('$baseUrl/api/projects/stop'),
      headers: _headers,
      body: jsonEncode({'time': time}),
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Stop timer failed');
    }
    return jsonDecode(resp.body);
  }

  Future<List<Map<String, dynamic>>> getProjects() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/projects/'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Projects failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Analytics ----

  /// Returns one entry per day in the given year (default: current year).
  /// Each entry: {date: 'YYYY-MM-DD', total_minutes: int, session_count: int, project_count: int}.
  ///
  /// Throws [ApiException] on non-200. See [getProjects] for the rationale.
  Future<List<Map<String, dynamic>>> getHeatmap({int? year}) async {
    final query = year != null ? '?year=$year' : '';
    final resp = await http.get(
      Uri.parse('$baseUrl/api/analytics/heatmap$query'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Heatmap failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Flow Score ----

  /// Throws [ApiException] on non-200. See [getProjects] for the rationale.
  Future<List<Map<String, dynamic>>> getFlowWindows(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/signals/flow-windows?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Flow windows failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  /// Single round-trip aggregate for a flow-window slice — mirrors
  /// `GET /api/signals/flow-windows/summary` on the API and the
  /// `GetFlowWindowsSummary` method on the daemon Go client.
  ///
  /// Returns null on any non-200 response so callers can render an
  /// empty state without parsing errors. The same filter params as
  /// `getFlowWindows` are accepted as optional named args; empty
  /// strings are dropped from the URL so the request stays clean.
  Future<Map<String, dynamic>?> getFlowWindowsSummary(
    String start,
    String end, {
    String? editorRepo,
    String? editorLanguage,
    String? bundleId,
    String? projectId,
  }) async {
    final params = <String, String>{'start': start, 'end': end};
    if (editorRepo != null && editorRepo.isNotEmpty) {
      params['editor_repo'] = editorRepo;
    }
    if (editorLanguage != null && editorLanguage.isNotEmpty) {
      params['editor_language'] = editorLanguage;
    }
    if (bundleId != null && bundleId.isNotEmpty) {
      params['bundle_id'] = bundleId;
    }
    if (projectId != null && projectId.isNotEmpty) {
      params['project_id'] = projectId;
    }
    final uri = Uri.parse('$baseUrl/api/signals/flow-windows/summary')
        .replace(queryParameters: params);
    final resp = await http.get(uri, headers: _headers);
    if (resp.statusCode != 200) return null;
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  /// Pending auto-timer suggestions for the notification poller. Each map
  /// carries `id` (dedupe key), `project_id`, `project_name`, `suggested_at`,
  /// and optionally `editor_repo`. Sorted newest-first by the API. Same
  /// transient-error behavior as [getRecentDrift] — returns `[]` rather
  /// than throwing.
  Future<List<Map<String, dynamic>>> getPendingSuggestions({
    DateTime? since,
    int limit = 20,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (since != null) {
      params['since'] = since.toUtc().toIso8601String();
    }
    final uri = Uri.parse('$baseUrl/api/signals/pending-suggestions')
        .replace(queryParameters: params);
    try {
      final resp = await http.get(uri, headers: _headers);
      if (resp.statusCode != 200) return const [];
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final suggestions = (body['suggestions'] as List?) ?? const [];
      return suggestions.cast<Map<String, dynamic>>();
    } catch (_) {
      return const [];
    }
  }

  /// Recent drift events for the notification poller. Each map carries
  /// `id` (dedupe key), `started_at` (ISO-8601 string), `duration_seconds`,
  /// and `bundle_id`. Sorted newest-first by the API. Returns an empty
  /// list (rather than throwing) on transient errors so a network blip
  /// doesn't break the poller's tick.
  Future<List<Map<String, dynamic>>> getRecentDrift({DateTime? since, int limit = 20}) async {
    final params = <String, String>{'limit': '$limit'};
    if (since != null) {
      params['since'] = since.toUtc().toIso8601String();
    }
    final uri = Uri.parse('$baseUrl/api/signals/recent-drift')
        .replace(queryParameters: params);
    try {
      final resp = await http.get(uri, headers: _headers);
      if (resp.statusCode != 200) return const [];
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final events = (body['events'] as List?) ?? const [];
      return events.cast<Map<String, dynamic>>();
    } catch (_) {
      return const [];
    }
  }

  /// Throws [ApiException] on non-200. See [getProjects] for the rationale.
  Future<List<Map<String, dynamic>>> getSignalSummaries(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/signals/summaries?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Signal summaries failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Coach ----

  Future<Map<String, dynamic>?> getTodayBrief() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/coach/brief/today'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return null;
    final body = resp.body;
    if (body.isEmpty || body == 'null') return null;
    return jsonDecode(body);
  }

  /// The coach conversation so far, oldest first. Each message carries
  /// `role` ('user' | 'assistant'), `content` and `conversation_id`.
  Future<List<Map<String, dynamic>>> getChatHistory({String? conversationId, int limit = 50}) async {
    final params = <String, String>{'limit': '$limit'};
    if (conversationId != null) params['conversation_id'] = conversationId;
    final uri = Uri.parse('$baseUrl/api/coach/chat/history').replace(queryParameters: params);
    final resp = await http.get(uri, headers: _headers);
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Chat history failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  /// Sends one message to the coach and yields its reply as the server's
  /// SSE events: `{type: 'text', text}`, `{type: 'tool_use', name}`,
  /// `{type: 'error', error, code}` and finally `{type: 'done',
  /// conversation_id}`. A non-200 throws before anything is yielded.
  Stream<Map<String, dynamic>> streamChat(String message, {String? conversationId}) async* {
    final request = http.Request('POST', Uri.parse('$baseUrl/api/coach/chat'))
      ..headers.addAll(_headers)
      ..body = jsonEncode({
        'message': message,
        // ignore: use_null_aware_elements
        if (conversationId != null) 'conversation_id': conversationId,
      });
    final client = http.Client();
    try {
      final resp = await client.send(request);
      if (resp.statusCode != 200) {
        throw _apiError(await http.Response.fromStream(resp), 'Coach chat failed');
      }
      yield* decodeSse(resp.stream);
    } finally {
      client.close();
    }
  }

  // ---- Beats ----

  /// The sessions that started on [utcDay] (a UTC calendar date — the API
  /// buckets `date_filter` in UTC). A local day can straddle two UTC days,
  /// so callers that want one local day ask for both and filter.
  Future<List<Map<String, dynamic>>> getBeatsOn(DateTime utcDay) async {
    final day = '${utcDay.year.toString().padLeft(4, '0')}-'
        '${utcDay.month.toString().padLeft(2, '0')}-'
        '${utcDay.day.toString().padLeft(2, '0')}';
    final resp = await http.get(
      Uri.parse('$baseUrl/api/beats/?date_filter=$day'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Sessions failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  /// Rewrites one session's times. `end: null` reopens it as the running
  /// timer, which is how a stop is undone and how a running timer's start
  /// is moved earlier.
  Future<Map<String, dynamic>> updateBeat({
    required String id,
    required String projectId,
    required DateTime start,
    DateTime? end,
  }) async {
    final resp = await http.put(
      Uri.parse('$baseUrl/api/beats/'),
      headers: _headers,
      body: jsonEncode({
        'id': id,
        'project_id': projectId,
        'start': start.toUtc().toIso8601String(),
        'end': end?.toUtc().toIso8601String(),
      }),
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Session update failed');
    }
    return jsonDecode(resp.body);
  }

  // ---- Projects ----

  /// The project's ledger: the last [weeks] weeks newest first (hours per
  /// day, the goal in force, a day job's expectation and closing balance)
  /// and `totals`, today's balance. Weeks are bucketed in [timezone].
  Future<Map<String, dynamic>> getLedger(String projectId, {int weeks = 1, String? timezone}) async {
    final params = <String, String>{'weeks': '$weeks'};
    if (timezone != null) params['tz'] = timezone;
    final uri = Uri.parse('$baseUrl/api/projects/$projectId/ledger').replace(queryParameters: params);
    final resp = await http.get(uri, headers: _headers);
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Ledger failed');
    }
    return jsonDecode(resp.body);
  }

  // ---- Calendar ----

  /// Calendar events between [start] and [end]: `summary`, `start`, `end`
  /// (ISO strings) and `all_day`. Empty when no calendar is connected.
  Future<List<Map<String, dynamic>>> getCalendarEvents(DateTime start, DateTime end) async {
    final uri = Uri.parse('$baseUrl/api/calendar/events').replace(queryParameters: {
      'start': start.toUtc().toIso8601String(),
      'end': end.toUtc().toIso8601String(),
    });
    final resp = await http.get(uri, headers: _headers);
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Calendar failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Biometrics ----

  /// Throws [ApiException] on non-200. See [getProjects] for the rationale.
  Future<List<Map<String, dynamic>>> getBiometrics(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/biometrics/?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw _apiError(resp, 'Biometrics failed');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }
}

/// Decodes a `text/event-stream` body into its JSON `data:` payloads.
/// Events are separated by a blank line; a `data: [DONE]` sentinel ends
/// the stream; lines that are not `data:` (comments, `event:`) and
/// payloads that are not JSON objects are skipped. Chunks may split an
/// event, or a line, anywhere.
Stream<Map<String, dynamic>> decodeSse(Stream<List<int>> bytes) async* {
  final buffer = StringBuffer();
  await for (final chunk in bytes.transform(utf8.decoder)) {
    buffer.write(chunk);
    var text = buffer.toString().replaceAll('\r\n', '\n');
    var cut = text.indexOf('\n\n');
    while (cut >= 0) {
      final event = text.substring(0, cut);
      text = text.substring(cut + 2);
      final data = event
          .split('\n')
          .where((l) => l.startsWith('data:'))
          .map((l) => l.substring(5).trimLeft())
          .join('\n');
      if (data == '[DONE]') return;
      if (data.isNotEmpty) {
        try {
          final decoded = jsonDecode(data);
          if (decoded is Map<String, dynamic>) yield decoded;
        } on FormatException {
          // A malformed event is dropped; the stream carries on.
        }
      }
      cut = text.indexOf('\n\n');
    }
    buffer
      ..clear()
      ..write(text);
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String message;

  /// Machine-readable code from the API's unified error envelope
  /// (api/src/beats/api/errors.py: `{detail, code, fields?}`). Null
  /// when the body isn't envelope-shaped (older API versions, proxy
  /// 502s with HTML, etc.). Callers that want to branch on
  /// "PROJECT_ARCHIVED vs RATE_LIMITED" use this — error toasts
  /// just need [message].
  final String? code;

  ApiException(this.statusCode, this.message, {this.code});

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Build the suffix that goes after "[verb] failed: " for an error
/// response. Tries the unified API error envelope first
/// (`{detail, code, fields?}`) so the user sees "Project archived
/// [PROJECT_ARCHIVED]" rather than a raw JSON blob; falls back to
/// the trimmed body text on non-JSON responses (proxy HTML 502s);
/// returns "(empty body)" for status-only failures so the toast
/// doesn't end with a trailing colon followed by nothing.
///
/// Mirrors the daemon-side `describeErrorBody` (Go) and the UI's
/// 422 fields[] surfacing in ApiError so all three surfaces tell
/// the user the same thing.
// Exposed for tests in companion/test/api_client_test.dart. Not
// part of the public ApiClient API; importers should use the
// ApiException it produces, not call this directly.
String describeErrorBody(String body) {
  final trimmed = body.trim();
  if (trimmed.isEmpty) return '(empty body)';
  try {
    final decoded = jsonDecode(trimmed);
    if (decoded is Map<String, dynamic>) {
      final detail = decoded['detail'];
      final code = decoded['code'];
      final fields = decoded['fields'];
      final fieldSuffix = _formatFields(fields);
      final detailStr = (detail is String && detail.isNotEmpty) ? detail : null;
      final codeStr = (code is String && code.isNotEmpty) ? code : null;
      if (detailStr != null && codeStr != null) {
        return fieldSuffix.isEmpty
            ? '$detailStr [$codeStr]'
            : '$detailStr [$codeStr]: $fieldSuffix';
      }
      if (detailStr != null) {
        return fieldSuffix.isEmpty ? detailStr : '$detailStr: $fieldSuffix';
      }
      if (codeStr != null) {
        return fieldSuffix.isEmpty ? codeStr : '$codeStr: $fieldSuffix';
      }
    }
  } on FormatException {
    // Body wasn't JSON — fall through to the trimmed-raw fallback.
  }
  return trimmed;
}

/// Render a 422 fields list ([{path, message, type}, ...]) as a
/// "name (field required), email (invalid format)" suffix. Returns
/// "" if the input isn't a list, every entry is empty, or the
/// caller passed null.
String _formatFields(Object? fields) {
  if (fields is! List) return '';
  final parts = <String>[];
  for (final entry in fields) {
    if (entry is! Map) continue;
    final path = (entry['path'] as Object?)?.toString().trim() ?? '';
    final message = (entry['message'] as Object?)?.toString().trim() ?? '';
    if (path.isEmpty && message.isEmpty) continue;
    if (path.isNotEmpty && message.isNotEmpty) {
      parts.add('$path ($message)');
    } else {
      parts.add(path.isEmpty ? message : path);
    }
  }
  return parts.join(', ');
}

/// Extracts code from the envelope (or null if not present), so
/// ApiException can carry a structured code for callers that want
/// to branch. Best-effort — silent null on any decode hiccup.
String? _envelopeCode(String body) {
  try {
    final decoded = jsonDecode(body);
    if (decoded is Map<String, dynamic>) {
      final code = decoded['code'];
      if (code is String && code.isNotEmpty) return code;
    }
  } on FormatException {
    // Non-JSON body, no code.
  }
  return null;
}

/// Build a fully-formatted ApiException for a non-200 [resp].
/// Centralizes the "verb failed: [suffix]" rendering so the 12+ throw
/// sites in [ApiClient] don't drift apart.
ApiException _apiError(http.Response resp, String verb) {
  final detail = describeErrorBody(resp.body);
  return ApiException(
    resp.statusCode,
    '$verb: $detail',
    code: _envelopeCode(resp.body),
  );
}
