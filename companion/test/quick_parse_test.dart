import 'package:beats_companion/services/quick_parse.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime(2026, 10, 14, 11, 5);

  group('parseQuick', () {
    test('a name alone starts now', () {
      final c = parseQuick('  studio   kite ', now);
      expect(c.verb, QuickVerb.start);
      expect(c.query, 'studio kite');
      expect(c.at, isNull);
    });

    test('from, since and at set a time today', () {
      for (final input in ['kite from 11:00', 'kite since 11:00', 'kite at 11:00', 'kite 11:00']) {
        final c = parseQuick(input, now);
        expect(c.query, 'kite', reason: input);
        expect(c.at, DateTime(2026, 10, 14, 11), reason: input);
      }
    });

    test('am and pm read on the twelve-hour clock', () {
      expect(parseQuick('kite 9:30am', now).at, DateTime(2026, 10, 14, 9, 30));
      expect(parseQuick('kite from 12am', now).at, DateTime(2026, 10, 14, 0));
      expect(parseQuick('kite 12pm', now).problem, isNotNull); // 12:00, still to come
    });

    test('a bare number after a name is part of the name', () {
      final c = parseQuick('route 66', now);
      expect(c.query, 'route 66');
      expect(c.at, isNull);
    });

    test('a bare hour after from is a time', () {
      expect(parseQuick('kite from 9', now).at, DateTime(2026, 10, 14, 9));
    });

    test('durations ago count back from now', () {
      expect(parseQuick('spanish 25m ago', now).at, DateTime(2026, 10, 14, 10, 40));
      expect(parseQuick('spanish 1h ago', now).at, DateTime(2026, 10, 14, 10, 5));
      expect(parseQuick('spanish 1h 30m ago', now).at, DateTime(2026, 10, 14, 9, 35));
      expect(parseQuick('spanish 1h 30m ago', now).query, 'spanish');
    });

    test('a time still to come is flagged, not silently used', () {
      final c = parseQuick('kite from 17:30', now);
      expect(c.at, DateTime(2026, 10, 14, 17, 30));
      expect(c.problem, '17:30 hasn\'t happened yet');
    });

    test('impossible clock times are left as words', () {
      expect(parseQuick('kite at 25:00', now).at, isNull);
      expect(parseQuick('kite at 13pm', now).at, isNull);
    });

    test('stop, with or without a time', () {
      expect(parseQuick('stop', now).verb, QuickVerb.stop);
      expect(parseQuick('Stop', now).at, isNull);
      expect(parseQuick('stop at 10:50', now).at, DateTime(2026, 10, 14, 10, 50));
      expect(parseQuick('stop 10m ago', now).at, DateTime(2026, 10, 14, 10, 55));
    });

    test('a project that starts with "stop" is not the stop command', () {
      final c = parseQuick('stopwatch app', now);
      expect(c.verb, QuickVerb.start);
      expect(c.query, 'stopwatch app');
    });
  });

  group('rankMatches', () {
    final names = ['Northwind', 'Studio Kite', 'Kite research', 'LifePete', 'Spanish'];

    test('prefix, then word start, then substring, then letters in order', () {
      expect(rankMatches('kite', names), [2, 1]);
      expect(rankMatches('pete', names), [3]);
      expect(rankMatches('nwd', names), [0]);
    });

    test('an empty query keeps every name in order', () {
      expect(rankMatches(' ', names), [0, 1, 2, 3, 4]);
    });

    test('no match is an empty list', () {
      expect(rankMatches('zzz', names), isEmpty);
    });
  });
}
