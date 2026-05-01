import 'package:shared_preferences/shared_preferences.dart';

class TokenStorage {
  static const _key = 'beats_device_token';
  static const _apiUrlKey = 'beats_api_url';
  static const _webUrlKey = 'beats_web_url';

  Future<String?> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key);
  }

  Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, token);
  }

  Future<void> deleteToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }

  Future<String> loadApiUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_apiUrlKey) ?? 'http://localhost:7999';
  }

  Future<void> saveApiUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_apiUrlKey, url);
  }

  /// The base URL of the Beats web UI — distinct from the API URL
  /// because deployments commonly host the API and the SPA on
  /// different hosts (api.example.com vs app.example.com). Default
  /// matches the daemon's [ui] base_url default so a fresh local-dev
  /// setup works without configuration. Used by the FlowScreen's
  /// "open in browser" deep links.
  Future<String> loadWebUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_webUrlKey) ?? 'http://localhost:8080';
  }

  Future<void> saveWebUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_webUrlKey, url);
  }
}
