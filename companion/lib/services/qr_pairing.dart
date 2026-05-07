import 'dart:convert';

/// Decoded QR pairing payload — what the scanner hands back to the
/// pairing screen so it can autofill and trigger the existing
/// `exchangePairCode` flow without the user retyping anything.
class QrPairingPayload {
  /// 6-character pairing code, normalized to uppercase.
  final String code;

  /// Optional API base URL. Present when the QR encoded a JSON or
  /// deep-link payload that included it; null when the QR was a bare
  /// 6-char code (in which case the pairing screen reuses whatever URL
  /// the user already typed / has saved).
  final String? apiUrl;

  const QrPairingPayload({required this.code, this.apiUrl});
}

/// Parse a QR-decoded string into a [QrPairingPayload]. Returns null when
/// the payload doesn't look like a Beats pairing QR.
///
/// Three accepted formats, in priority order:
///
/// 1. **JSON**: `{"code": "ABC123", "api": "https://api.example.com"}` —
///    the format the web Settings page emits when generating a QR. Wins
///    if it parses cleanly with both fields. Pulls the user straight
///    into a one-tap pair regardless of what API URL the device has
///    saved (fresh-install flow).
/// 2. **Deep link**: `beats://pair/ABC123` — short, easy to encode by
///    hand if the user wants to type a QR generator's URL. No API URL
///    carried; the pairing screen falls back to its saved value.
/// 3. **Plain code**: `ABC123` — anything that's exactly 6 alphanumeric
///    characters after trimming + uppercasing.
///
/// The 6-char code constraint matches the daemon's `pairing_code` format
/// and the validation in `_pair()` on the existing pairing screen.
QrPairingPayload? parseQrPairingPayload(String? raw) {
  if (raw == null) return null;
  final text = raw.trim();
  if (text.isEmpty) return null;

  // 1. JSON
  if (text.startsWith('{') && text.endsWith('}')) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map<String, dynamic>) {
        final code = decoded['code'];
        final api = decoded['api'] ?? decoded['api_url'] ?? decoded['apiUrl'];
        if (code is String) {
          final normalized = _normalizeCode(code);
          if (normalized != null) {
            return QrPairingPayload(
              code: normalized,
              apiUrl: api is String && api.trim().isNotEmpty ? api.trim() : null,
            );
          }
        }
      }
    } catch (_) {
      // Fall through to the other formats — a malformed JSON-ish blob is
      // still worth checking against the deep-link / plain patterns.
    }
  }

  // 2. Deep link
  const scheme = 'beats://pair/';
  if (text.toLowerCase().startsWith(scheme)) {
    final code = text.substring(scheme.length);
    final normalized = _normalizeCode(code);
    if (normalized != null) {
      return QrPairingPayload(code: normalized);
    }
  }

  // 3. Plain code
  final normalized = _normalizeCode(text);
  if (normalized != null) {
    return QrPairingPayload(code: normalized);
  }

  return null;
}

/// Trim, uppercase, and verify the input is 6 alphanumeric characters.
/// Anything else returns null — the pairing endpoint enforces the same
/// shape, so accepting more here would just produce a 404 round-trip.
String? _normalizeCode(String raw) {
  final trimmed = raw.trim().toUpperCase();
  if (trimmed.length != 6) return null;
  if (!RegExp(r'^[A-Z0-9]{6}$').hasMatch(trimmed)) return null;
  return trimmed;
}
