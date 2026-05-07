// Tests for TokenStorage. Locks in the storage backends (secure for the
// device token, SharedPreferences for the URLs), the key names (changing
// them silently would orphan existing user data), the default URL
// fallbacks, and the one-shot SharedPreferences -> secure-store migration
// for installs upgrading from <= 1.0.0.

import 'package:beats_companion/services/secure_store.dart';
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
      final s = TokenStorage(secure: MemorySecureStore());
      expect(await s.loadToken(), isNull);
    });

    test('save then load round-trips the device token', () async {
      final s = TokenStorage(secure: MemorySecureStore());
      await s.saveToken('dev-token-abc');
      expect(await s.loadToken(), 'dev-token-abc');
    });

    test('deleteToken clears a previously-stored token', () async {
      final s = TokenStorage(secure: MemorySecureStore());
      await s.saveToken('dev-token-abc');
      await s.deleteToken();
      expect(await s.loadToken(), isNull);
    });

    test('persists across separate TokenStorage instances against the same secure store', () async {
      // Both instances share the secure store, so a write through one shows
      // up via the other — important for the pairing flow which writes from
      // one screen and reads from another via fresh constructions.
      final secure = MemorySecureStore();
      await TokenStorage(secure: secure).saveToken('persist-me');
      expect(await TokenStorage(secure: secure).loadToken(), 'persist-me');
    });

    test('one-shot migration: legacy SharedPreferences token is promoted to secure storage and the prefs copy is cleared', () async {
      // Versions <= 1.0.0 stored the device token under this same key in
      // plaintext SharedPreferences. The first loadToken() after the
      // migration must surface that token AND clear the prefs copy so the
      // plaintext can't be recovered later (e.g. via an unencrypted device
      // backup).
      SharedPreferences.setMockInitialValues({
        'beats_device_token': 'legacy-token-xyz',
      });
      final secure = MemorySecureStore();
      final s = TokenStorage(secure: secure);

      expect(await s.loadToken(), 'legacy-token-xyz');

      // Migration side-effects.
      expect(await secure.read('beats_device_token'), 'legacy-token-xyz');
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('beats_device_token'), isNull);
    });

    test('saveToken clears any stale legacy SharedPreferences token', () async {
      // Belt-and-braces: an explicit save during the migration window
      // should also drop the legacy copy, so a later loadToken() can't
      // accidentally resurrect a token the user just rotated.
      SharedPreferences.setMockInitialValues({
        'beats_device_token': 'old-leftover',
      });
      final secure = MemorySecureStore();
      await TokenStorage(secure: secure).saveToken('new-token');

      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('beats_device_token'), isNull);
      expect(await secure.read('beats_device_token'), 'new-token');
    });

    test('deleteToken clears both secure storage and any legacy prefs copy', () async {
      SharedPreferences.setMockInitialValues({
        'beats_device_token': 'old-leftover',
      });
      final secure = MemorySecureStore({'beats_device_token': 'current'});
      await TokenStorage(secure: secure).deleteToken();

      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('beats_device_token'), isNull);
      expect(await secure.read('beats_device_token'), isNull);
    });
  });

  group('TokenStorage API URL', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('loadApiUrl returns the default localhost URL when nothing saved', () async {
      // Default is the local dev API. Self-hosted users override this via
      // the pairing screen; the constant lives in TokenStorage so the rest
      // of the app doesn't need a #define.
      final s = TokenStorage(secure: MemorySecureStore());
      expect(await s.loadApiUrl(), 'http://localhost:7999');
    });

    test('saveApiUrl persists the override', () async {
      final s = TokenStorage(secure: MemorySecureStore());
      await s.saveApiUrl('https://api.example.com');
      expect(await s.loadApiUrl(), 'https://api.example.com');
    });

    test('saveApiUrl overrides a previously-saved value', () async {
      final s = TokenStorage(secure: MemorySecureStore());
      await s.saveApiUrl('https://first.example.com');
      await s.saveApiUrl('https://second.example.com');
      expect(await s.loadApiUrl(), 'https://second.example.com');
    });
  });

  group('TokenStorage web URL', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('loadWebUrl defaults to http://localhost:8080 when nothing saved', () async {
      // Matches the daemon's [ui] base_url default. Locked in so a refactor
      // can't silently flip the local-dev port and break the FlowScreen
      // deep links.
      final s = TokenStorage(secure: MemorySecureStore());
      expect(await s.loadWebUrl(), 'http://localhost:8080');
    });

    test('saveWebUrl persists the override', () async {
      final s = TokenStorage(secure: MemorySecureStore());
      await s.saveWebUrl('https://app.example.com');
      expect(await s.loadWebUrl(), 'https://app.example.com');
    });

    test('web URL is independent from API URL — distinct prefs keys', () async {
      // Self-hosted users typically have api.example.com and
      // app.example.com on different hosts. Saving one must not affect the
      // other.
      final s = TokenStorage(secure: MemorySecureStore());
      await s.saveApiUrl('https://api.example.com');
      await s.saveWebUrl('https://app.example.com');
      expect(await s.loadApiUrl(), 'https://api.example.com');
      expect(await s.loadWebUrl(), 'https://app.example.com');
    });
  });
}
