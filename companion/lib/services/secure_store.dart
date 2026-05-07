import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Tiny abstraction over OS-level secure storage so [TokenStorage] can be
/// unit-tested without booting any platform channels. The real
/// implementation wraps `flutter_secure_storage` (Keychain on iOS/macOS,
/// EncryptedSharedPreferences on Android, DPAPI on Windows, libsecret on
/// Linux); tests pass an in-memory implementation.
abstract class SecureStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

/// Production [SecureStore] backed by `flutter_secure_storage`.
///
/// Android uses EncryptedSharedPreferences (rather than the plain
/// SharedPreferences blob the package falls back to on older Androids) so
/// the key material lands behind the Android Keystore. iOS uses
/// `first_unlock` Keychain accessibility — the token is readable after the
/// device is unlocked once post-boot, which is the right level for a
/// background-syncing companion that needs to push biometrics overnight
/// without the user re-unlocking the phone.
class FlutterSecureStore implements SecureStore {
  final FlutterSecureStorage _backing;

  FlutterSecureStore()
      : _backing = const FlutterSecureStorage(
          aOptions: AndroidOptions(encryptedSharedPreferences: true),
          iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
        );

  @override
  Future<String?> read(String key) => _backing.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _backing.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _backing.delete(key: key);
}

/// In-memory [SecureStore] for tests. Backed by a plain map; reads/writes
/// are trivially synchronous under the async signature.
class MemorySecureStore implements SecureStore {
  final Map<String, String> _backing;

  MemorySecureStore([Map<String, String>? initial])
      : _backing = {...?initial};

  @override
  Future<String?> read(String key) async => _backing[key];

  @override
  Future<void> write(String key, String value) async {
    _backing[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _backing.remove(key);
  }
}
