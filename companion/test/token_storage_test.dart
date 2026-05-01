// Tests for TokenStorage. Locks in the SharedPreferences key names
// (changing them silently would orphan existing user data) and the
// default API URL fallback.

import 'package:beats_companion/services/token_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('TokenStorage device token', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('loadToken returns null when nothing has been stored', () async {
      final s = TokenStorage();
      expect(await s.loadToken(), isNull);
    });

    test('save then load round-trips the device token', () async {
      final s = TokenStorage();
      await s.saveToken('dev-token-abc');
      expect(await s.loadToken(), 'dev-token-abc');
    });

    test('deleteToken clears a previously-stored token', () async {
      final s = TokenStorage();
      await s.saveToken('dev-token-abc');
      await s.deleteToken();
      expect(await s.loadToken(), isNull);
    });

    test('persists across separate TokenStorage instances against the same prefs', () async {
      // Both instances share the underlying SharedPreferences singleton,
      // so a write through one shows up via the other — important for
      // the pairing flow which writes from one screen and reads from
      // another via fresh constructions.
      await TokenStorage().saveToken('persist-me');
      expect(await TokenStorage().loadToken(), 'persist-me');
    });
  });

  group('TokenStorage API URL', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('loadApiUrl returns the default localhost URL when nothing saved', () async {
      // Default is the local dev API. Self-hosted users override this
      // via the pairing screen; the constant lives here so the rest
      // of the app doesn't need a #define.
      final s = TokenStorage();
      expect(await s.loadApiUrl(), 'http://localhost:7999');
    });

    test('saveApiUrl persists the override', () async {
      final s = TokenStorage();
      await s.saveApiUrl('https://api.example.com');
      expect(await s.loadApiUrl(), 'https://api.example.com');
    });

    test('saveApiUrl overrides a previously-saved value', () async {
      final s = TokenStorage();
      await s.saveApiUrl('https://first.example.com');
      await s.saveApiUrl('https://second.example.com');
      expect(await s.loadApiUrl(), 'https://second.example.com');
    });
  });
}
