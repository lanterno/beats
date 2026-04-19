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
}

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}
