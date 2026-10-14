import 'package:beats_companion/services/time_format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('formatMinutes', () {
    test('pads minutes only once there are hours', () {
      expect(formatMinutes(0), '0m');
      expect(formatMinutes(-5), '0m');
      expect(formatMinutes(7), '7m');
      expect(formatMinutes(60), '1h');
      expect(formatMinutes(64), '1h 04m');
      expect(formatMinutes(1154), '19h 14m');
    });
  });

  group('formatClock', () {
    test('drops the hour under an hour and keeps seconds padded', () {
      expect(formatClock(const Duration(seconds: 5)), '0:05');
      expect(formatClock(const Duration(minutes: 24, seconds: 7)), '24:07');
      expect(formatClock(const Duration(hours: 1, minutes: 24, seconds: 7)), '1:24:07');
      expect(formatClock(const Duration(hours: 12)), '12:00:00');
    });

    test('reads clock skew as zero', () {
      expect(formatClock(const Duration(seconds: -3)), '0:00');
    });
  });

  group('formatShortClock', () {
    test('minutes under an hour, h:mm from there', () {
      expect(formatShortClock(const Duration(minutes: 9, seconds: 59)), '9m');
      expect(formatShortClock(const Duration(hours: 1, minutes: 4)), '1:04');
      expect(formatShortClock(const Duration(seconds: -1)), '0m');
    });
  });

  group('formatBalance', () {
    test('signs and rounds to the minute', () {
      expect(formatBalance(1 + 10 / 60), '+1h 10m');
      expect(formatBalance(-25 / 60), '−25m');
      expect(formatBalance(0.004), '±0m');
    });
  });
}
