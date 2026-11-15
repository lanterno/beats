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

  /// Optional web app base URL, which the web's QR carries beside `api`
  /// (`ui/client/pages/settings/pairingQr.ts`) unless it is a loopback
  /// address. Null when the QR named none.
  final String? webUrl;

  const QrPairingPayload({required this.code, this.apiUrl, this.webUrl});
}

/// Whether pairing with [scannedApi] would point this device at a server
/// other than [currentApi], the one it would use otherwise (the saved one,
/// else the build's). Compared by origin, so a change of scheme or port
/// counts too. A QR that names no server changes nothing; one scanned with
/// no current server is a change, since there is nothing it agrees with.
///
/// This is what asks before a QR from some other host takes over a fresh
/// install, and with it everything the device later uploads (#325).
bool qrChangesServer(String? scannedApi, String? currentApi) {
  if (scannedApi == null) return false;
  final scanned = _origin(scannedApi);
  final current = currentApi == null ? null : _origin(currentApi);
  return scanned == null || current == null || scanned != current;
}

String? _origin(String url) {
  final uri = Uri.tryParse(url.trim());
  if (uri == null || uri.host.isEmpty) return null;
  final port = uri.hasPort ? ':${uri.port}' : '';
  return '${uri.scheme.toLowerCase()}://${uri.host.toLowerCase()}$port';
}

/// The web address to keep after pairing from [payload]: null to leave
/// the stored one alone (the QR named no server), else the QR's own, else
/// an empty string, which clears it. A QR for another server with no web
/// address must not leave this device linking into lifepete.com: no web
/// links is better than wrong ones (#325).
String? webUrlAfterScan(QrPairingPayload payload) {
  if (payload.apiUrl == null) return null;
  return payload.webUrl ?? '';
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
        final web = decoded['web'] ?? decoded['web_url'] ?? decoded['webUrl'];
        if (code is String) {
          final normalized = _normalizeCode(code);
          if (normalized != null) {
            return QrPairingPayload(
              code: normalized,
              apiUrl: api is String && api.trim().isNotEmpty ? api.trim() : null,
              webUrl: web is String && web.trim().isNotEmpty ? web.trim() : null,
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
