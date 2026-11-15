// Tests for parseQrPairingPayload — the pure pairing-QR decoder used by
// the mobile QR pairing screen. Locks in the JSON > deep-link > plain
// priority order, the 6-char alphanumeric normalization, and the
// rejection of obvious garbage so the camera scanner never tries to
// pair with a coffee-shop wifi QR.

import 'package:beats_companion/services/qr_pairing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('parseQrPairingPayload — happy path', () {
    test('plain 6-char code', () {
      final p = parseQrPairingPayload('ABC123');
      expect(p, isNotNull);
      expect(p!.code, 'ABC123');
      expect(p.apiUrl, isNull);
    });

    test('plain code is uppercased', () {
      final p = parseQrPairingPayload('abc123');
      expect(p, isNotNull);
      expect(p!.code, 'ABC123');
    });

    test('plain code is trimmed', () {
      final p = parseQrPairingPayload('  ABC123  ');
      expect(p, isNotNull);
      expect(p!.code, 'ABC123');
    });

    test('beats:// deep link', () {
      final p = parseQrPairingPayload('beats://pair/XYZ789');
      expect(p, isNotNull);
      expect(p!.code, 'XYZ789');
      expect(p.apiUrl, isNull);
    });

    test('deep link scheme is case-insensitive', () {
      // QR generators occasionally upper-case the whole URL. The Beats
      // pairing scheme should still resolve.
      final p = parseQrPairingPayload('BEATS://PAIR/abc999');
      expect(p, isNotNull);
      expect(p!.code, 'ABC999');
    });

    test('JSON with both code and api', () {
      // The richest payload — the web Settings page emits this so a
      // fresh-install device can pair without typing the API URL.
      final p = parseQrPairingPayload(
          '{"code": "ABC123", "api": "https://api.example.com"}');
      expect(p, isNotNull);
      expect(p!.code, 'ABC123');
      expect(p.apiUrl, 'https://api.example.com');
    });

    test('JSON accepts api_url and apiUrl aliases', () {
      // Defensive: don't make the web side guess which key the client
      // wants. snake_case and camelCase both work.
      expect(parseQrPairingPayload(
              '{"code": "AAA111", "api_url": "https://x"}')!.apiUrl,
          'https://x');
      expect(parseQrPairingPayload(
              '{"code": "AAA111", "apiUrl": "https://y"}')!.apiUrl,
          'https://y');
    });

    test('JSON without api still returns code', () {
      // Older web versions might emit just the code as JSON. Still
      // usable — the pairing screen falls back to the saved API URL.
      final p = parseQrPairingPayload('{"code": "ZZZ999"}');
      expect(p, isNotNull);
      expect(p!.code, 'ZZZ999');
      expect(p.apiUrl, isNull);
    });

    test('JSON whose code field needs normalization is still accepted', () {
      final p = parseQrPairingPayload('{"code": "  abc999  "}');
      expect(p, isNotNull);
      expect(p!.code, 'ABC999');
    });
  });

  group('parseQrPairingPayload — rejects', () {
    test('null and empty', () {
      expect(parseQrPairingPayload(null), isNull);
      expect(parseQrPairingPayload(''), isNull);
      expect(parseQrPairingPayload('   '), isNull);
    });

    test('plain code wrong length', () {
      // The pairing endpoint enforces 6 chars; reject upstream so the
      // scanner doesn't pair-fail with a 404 round-trip.
      expect(parseQrPairingPayload('ABC12'), isNull); // 5
      expect(parseQrPairingPayload('ABC1234'), isNull); // 7
    });

    test('plain code with non-alphanumeric characters', () {
      expect(parseQrPairingPayload('ABC-12'), isNull);
      expect(parseQrPairingPayload('ABC 12'), isNull);
      expect(parseQrPairingPayload('ABC.12'), isNull);
    });

    test('non-Beats deep link', () {
      // A wifi QR (`WIFI:T:WPA;S:Cafe;P:hunter2;;`) or similar shouldn't
      // accidentally try to pair.
      expect(parseQrPairingPayload('WIFI:T:WPA;S:Cafe;P:hunter2;;'), isNull);
      expect(parseQrPairingPayload('https://example.com/pair/ABC123'), isNull);
    });

    test('beats deep link with bad code shape', () {
      expect(parseQrPairingPayload('beats://pair/short'), isNull);
      expect(parseQrPairingPayload('beats://pair/has-dashes'), isNull);
      expect(parseQrPairingPayload('beats://pair/'), isNull);
    });

    test('JSON with missing or wrong-typed code', () {
      expect(parseQrPairingPayload('{"api": "https://x"}'), isNull);
      expect(parseQrPairingPayload('{"code": 123456}'), isNull);
    });

    test('JSON-shaped but malformed text', () {
      // Not valid JSON; falls through to deep-link / plain checks, which
      // also fail → null.
      expect(parseQrPairingPayload('{not valid json}'), isNull);
    });

    test('JSON whose code fails the 6-char shape check', () {
      expect(parseQrPairingPayload('{"code": "TOOSHORT"}'), isNull);
      expect(parseQrPairingPayload('{"code": "no"}'), isNull);
    });
  });

  group('the web address a QR carries', () {
    test('the web QR carries both addresses', () {
      final p = parseQrPairingPayload(
          '{"code": "ABC123", "api": "https://api.lifepete.com", "web": "https://lifepete.com"}');
      expect(p!.apiUrl, 'https://api.lifepete.com');
      expect(p.webUrl, 'https://lifepete.com');
    });

    test('a blank web address is none', () {
      final p = parseQrPairingPayload('{"code": "ABC123", "api": "https://api.example.com", "web": " "}');
      expect(p!.webUrl, isNull);
    });

    test('a QR for a server with no web app clears the stored address', () {
      final p = parseQrPairingPayload('{"code": "ABC123", "api": "https://api.example.com"}')!;
      expect(webUrlAfterScan(p), '');
    });

    test('a QR with its web app keeps that address', () {
      final p = parseQrPairingPayload(
          '{"code": "ABC123", "api": "https://api.example.com", "web": "https://app.example.com"}')!;
      expect(webUrlAfterScan(p), 'https://app.example.com');
    });

    test('a QR that names no server leaves the stored address alone', () {
      expect(webUrlAfterScan(parseQrPairingPayload('ABC123')!), isNull);
      expect(webUrlAfterScan(parseQrPairingPayload('beats://pair/ABC123')!), isNull);
    });
  });

  group('qrChangesServer — when a scanned QR has to ask first', () {
    test('the server this device would use anyway stays one tap', () {
      expect(qrChangesServer('https://api.lifepete.com', 'https://api.lifepete.com'), isFalse);
      // Same origin, written differently.
      expect(qrChangesServer('https://API.lifepete.com/', 'https://api.lifepete.com'), isFalse);
    });

    test('a QR that names no server changes nothing', () {
      expect(qrChangesServer(null, 'https://api.lifepete.com'), isFalse);
      expect(qrChangesServer(null, null), isFalse);
    });

    test('another host asks', () {
      expect(qrChangesServer('https://api.attacker.example', 'https://api.lifepete.com'), isTrue);
    });

    test('another scheme or port on the same host asks too', () {
      expect(qrChangesServer('http://api.lifepete.com', 'https://api.lifepete.com'), isTrue);
      expect(qrChangesServer('https://api.lifepete.com:8443', 'https://api.lifepete.com'), isTrue);
    });

    test('with no server to compare against, any server asks', () {
      expect(qrChangesServer('https://api.example.com', null), isTrue);
    });

    test('an address with no host asks rather than passes', () {
      expect(qrChangesServer('not a url', 'https://api.lifepete.com'), isTrue);
    });
  });
}
