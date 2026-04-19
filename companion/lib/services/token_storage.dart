import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStorage {
  static const _key = 'beats_device_token';
  static const _apiUrlKey = 'beats_api_url';
  final _storage = const FlutterSecureStorage();

  Future<String?> loadToken() => _storage.read(key: _key);

  Future<void> saveToken(String token) => _storage.write(key: _key, value: token);

  Future<void> deleteToken() => _storage.delete(key: _key);

  Future<String> loadApiUrl() async {
    return await _storage.read(key: _apiUrlKey) ?? 'http://localhost:7999';
  }

  Future<void> saveApiUrl(String url) => _storage.write(key: _apiUrlKey, value: url);
}
