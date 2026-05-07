import 'package:shared_preferences/shared_preferences.dart';
import 'secure_store.dart';

/// Persists the device token (in OS-level secure storage) and the
/// API / web URLs (in plain SharedPreferences — they're not secrets).
///
/// The token used to live in SharedPreferences alongside the URLs. Versions
/// shipped <= 1.0.0 still have it there; [loadToken] performs a one-shot
/// migration on first read so existing installs don't get logged out.
class TokenStorage {
  static const _tokenKey = 'beats_device_token';
  static const _apiUrlKey = 'beats_api_url';
  static const _webUrlKey = 'beats_web_url';

  final SecureStore _secure;

  TokenStorage({SecureStore? secure}) : _secure = secure ?? FlutterSecureStore();

  /// Returns the device token, or null if the user hasn't paired yet.
  ///
  /// On first call after the migration, if the secure store is empty but a
  /// legacy plaintext token exists in SharedPreferences, copy it into the
  /// secure store and clear the prefs key — so the plaintext can't be
  /// recovered later (e.g. via a device backup).
  Future<String?> loadToken() async {
    String? fromSecure;
    try {
      fromSecure = await _secure.read(_tokenKey);
    } catch (_) {
      // Keychain unreachable (sandbox/entitlement edge cases on macOS, locked
      // device on iOS before first unlock). Fall through to the legacy path
      // — better to authenticate with a plaintext token than to wedge the
      // app on a spinner.
      fromSecure = null;
    }
    if (fromSecure != null) return fromSecure;

    final prefs = await SharedPreferences.getInstance();
    final legacy = prefs.getString(_tokenKey);
    if (legacy == null) return null;

    // Best-effort migration: if the keychain write fails, the user is still
    // authenticated for this session — we'll try again on next launch.
    try {
      await _secure.write(_tokenKey, legacy);
      await prefs.remove(_tokenKey);
    } catch (_) {}
    return legacy;
  }

  Future<void> saveToken(String token) async {
    await _secure.write(_tokenKey, token);
    // Drop any leftover legacy copy so a later migration round-trip can't
    // resurrect a stale token.
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  Future<void> deleteToken() async {
    await _secure.delete(_tokenKey);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  // ── URLs ─────────────────────────────────────────────────────────────
  // Not secrets, kept in plain SharedPreferences. Survives a Keychain wipe
  // (which would legitimately blow away the token but shouldn't reset the
  // user's self-hosted server URL).

  Future<String> loadApiUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_apiUrlKey) ?? 'http://localhost:7999';
  }

  Future<void> saveApiUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_apiUrlKey, url);
  }

  /// The base URL of the Beats web UI — distinct from the API URL because
  /// deployments commonly host the API and the SPA on different hosts
  /// (api.example.com vs app.example.com). Default matches the daemon's
  /// `[ui] base_url` default so a fresh local-dev setup works without
  /// configuration. Used by the FlowScreen's "open in browser" deep links.
  Future<String> loadWebUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_webUrlKey) ?? 'http://localhost:8080';
  }

  Future<void> saveWebUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_webUrlKey, url);
  }
}
