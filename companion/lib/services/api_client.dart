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
      throw ApiException(resp.statusCode, 'Pairing failed: ${resp.body}');
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
      throw ApiException(resp.statusCode, 'Heartbeat failed: ${resp.body}');
    }
  }

  Future<void> postBiometricDay(Map<String, dynamic> data) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/biometrics/daily'),
      headers: _headers,
      body: jsonEncode(data),
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Biometric push failed: ${resp.body}');
    }
  }

  Future<Map<String, dynamic>> getFitbitAuthUrl() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/fitbit/auth-url'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Failed to get Fitbit auth URL');
    }
    return jsonDecode(resp.body);
  }

  Future<Map<String, dynamic>> getFitbitStatus() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/fitbit/status'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Failed to get Fitbit status');
    }
    return jsonDecode(resp.body);
  }

  Future<Map<String, dynamic>> getOuraStatus() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/oura/status'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Failed to get Oura status');
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
      throw ApiException(resp.statusCode, 'Oura connection failed: ${resp.body}');
    }
  }

  Future<void> disconnectOura() async {
    final resp = await http.delete(
      Uri.parse('$baseUrl/api/oura/disconnect'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Oura disconnect failed');
    }
  }

  Future<void> disconnectFitbit() async {
    final resp = await http.delete(
      Uri.parse('$baseUrl/api/fitbit/disconnect'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Fitbit disconnect failed');
    }
  }

  // ---- Timer ----

  Future<Map<String, dynamic>> getTimerStatus() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/timer/status'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Timer status failed: ${resp.body}');
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
      throw ApiException(resp.statusCode, 'Start timer failed: ${resp.body}');
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
      throw ApiException(resp.statusCode, 'Stop timer failed: ${resp.body}');
    }
    return jsonDecode(resp.body);
  }

  /// Updates an existing beat in place. The API requires the full beat shape;
  /// callers typically pass the dict returned by [stopTimer] with the user's
  /// edits applied (note, tags).
  Future<void> updateBeat(Map<String, dynamic> beat) async {
    final resp = await http.put(
      Uri.parse('$baseUrl/api/beats/'),
      headers: _headers,
      body: jsonEncode(beat),
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Update beat failed: ${resp.body}');
    }
  }

  Future<List<Map<String, dynamic>>> getProjects() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/projects/'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Projects failed: ${resp.body}');
    }
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Analytics ----

  /// Returns the union of all tags this user has ever attached to a beat,
  /// alphabetized. Used by the post-stop sheet to surface chips.
  Future<List<String>> getTags() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/analytics/tags'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<String>();
  }

  /// Returns one entry per day in the given year (default: current year).
  /// Each entry: {date: 'YYYY-MM-DD', total_minutes: int, session_count: int, project_count: int}.
  Future<List<Map<String, dynamic>>> getHeatmap({int? year}) async {
    final query = year != null ? '?year=$year' : '';
    final resp = await http.get(
      Uri.parse('$baseUrl/api/analytics/heatmap$query'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Flow Score ----

  Future<List<Map<String, dynamic>>> getFlowWindows(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/signals/flow-windows?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
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

  Future<List<Map<String, dynamic>>> getSignalSummaries(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/signals/summaries?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
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

  Future<Map<String, dynamic>?> getTodayReview() async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/coach/review/today'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return null;
    final body = resp.body;
    if (body.isEmpty || body == 'null') return null;
    return jsonDecode(body);
  }

  Future<void> answerReview(String date, int questionIndex, String answer) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/coach/review/answer'),
      headers: _headers,
      body: jsonEncode({
        'date': date,
        'question_index': questionIndex,
        'answer': answer,
      }),
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Save review answer failed: ${resp.body}');
    }
  }

  // ---- Intentions ----

  Future<List<Map<String, dynamic>>> getIntentions({String? date}) async {
    final query = date != null ? '?target_date=$date' : '';
    final resp = await http.get(
      Uri.parse('$baseUrl/api/intentions$query'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createIntention(String projectId, int plannedMinutes) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/intentions'),
      headers: _headers,
      body: jsonEncode({'project_id': projectId, 'planned_minutes': plannedMinutes}),
    );
    if (resp.statusCode != 201) {
      throw ApiException(resp.statusCode, 'Create intention failed: ${resp.body}');
    }
    return jsonDecode(resp.body);
  }

  Future<void> toggleIntention(String id, bool completed) async {
    await http.patch(
      Uri.parse('$baseUrl/api/intentions/$id'),
      headers: _headers,
      body: jsonEncode({'completed': completed}),
    );
  }

  // ---- Daily Notes ----

  /// Upserts today's daily note. The API is keyed on (user, date) so calling
  /// this multiple times with different mood/note values overwrites in place.
  Future<void> upsertDailyNote({int? mood, String? note, String? date}) async {
    final body = <String, dynamic>{};
    if (date != null) body['date'] = date;
    if (mood != null) body['mood'] = mood;
    if (note != null) body['note'] = note;
    final resp = await http.put(
      Uri.parse('$baseUrl/api/daily-notes'),
      headers: _headers,
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw ApiException(resp.statusCode, 'Save daily note failed: ${resp.body}');
    }
  }

  /// Returns daily notes between [start] and [end], inclusive (YYYY-MM-DD).
  /// Used by the mood sparkline on the coach screen.
  Future<List<Map<String, dynamic>>> getDailyNotesRange(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/daily-notes/range?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  // ---- Biometrics ----

  Future<List<Map<String, dynamic>>> getBiometrics(String start, String end) async {
    final resp = await http.get(
      Uri.parse('$baseUrl/api/biometrics/?start=$start&end=$end'),
      headers: _headers,
    );
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}
