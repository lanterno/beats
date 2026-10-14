import 'package:beats_companion/services/body_story.dart';
import 'package:beats_companion/services/day_ribbon.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final day = DateTime(2026, 10, 14);
  DateTime at(int h, [int m = 0]) => DateTime(2026, 10, 14, h, m);

  group('dayWindowFor', () {
    test('defaults to 7:00–20:00', () {
      final w = dayWindowFor(day, [at(11, 5)]);
      expect(w.start, at(7));
      expect(w.end, at(20));
    });

    test('widens to whole hours around early and late marks', () {
      final w = dayWindowFor(day, [at(5, 40), at(21, 10)]);
      expect(w.start, at(5));
      expect(w.end, at(22));
    });

    test('a mark exactly on the hour does not add an hour', () {
      expect(dayWindowFor(day, [at(21)]).end, at(21));
    });

    test('a session from yesterday or into tomorrow stops at the midnights', () {
      final w = dayWindowFor(day, [DateTime(2026, 10, 13, 23), DateTime(2026, 10, 15, 1)]);
      expect(w.start, at(0));
      expect(w.end, DateTime(2026, 10, 15));
    });
  });

  group('placeSpans', () {
    final w = DayWindow(at(7), at(20));

    test('places a span by its share of the window', () {
      final placed = placeSpans(w, [(at(9, 36), at(13, 54), 'a')], now: at(14));
      expect(placed.single.left, closeTo(0.2, 1e-9));
      expect(placed.single.width, closeTo(258 / 780, 1e-9));
    });

    test('clips a span that starts before the window and drops one outside it', () {
      final placed = placeSpans(w, [(at(6), at(8), 'early'), (at(20, 30), at(21), 'late')], now: at(14));
      expect(placed.map((p) => p.item), ['early']);
      expect(placed.single.left, 0);
    });

    test('an open span runs to now', () {
      final placed = placeSpans(w, [(at(13), null, 'running')], now: at(14, 18));
      expect(placed.single.width, closeTo(78 / 780, 1e-9));
    });
  });

  group('flowBuckets', () {
    test('averages the windows in each quarter hour and leaves gaps empty', () {
      final w = DayWindow(at(9), at(10));
      final buckets = flowBuckets(w, [
        (at(9, 1), 0.5),
        (at(9, 14), 0.7),
        (at(9, 45), 0.9),
        (at(8, 59), 1.0), // before the window
        (at(10), 1.0), // at its end
      ]);
      expect(buckets.length, 4);
      expect(buckets[0], closeTo(0.6, 1e-9));
      expect(buckets[1], isNull);
      expect(buckets[3], 0.9);
    });
  });

  group('briefExcerpt', () {
    test('strips markdown and keeps a short brief whole', () {
      expect(briefExcerpt('## Today\n\n**Protect** the _morning_.'), 'Today Protect the morning.');
    });

    test('cuts at the last sentence end that fits', () {
      final body = 'First sentence here. Second one is longer than the budget allows by far.';
      expect(briefExcerpt(body, max: 40), 'First sentence here.');
    });

    test('cuts at a word with an ellipsis when one sentence is too long', () {
      expect(briefExcerpt('one two three four five six', max: 12), 'one two…');
    });

    test('nothing to say is null', () {
      expect(briefExcerpt(null), isNull);
      expect(briefExcerpt('  \n '), isNull);
    });
  });

  group('BodyWeek', () {
    final week = BodyWeek([
      {'date': '2026-10-12', 'source': 'oura', 'hrv_ms': 41, 'readiness_score': 70},
      {'date': '2026-10-13', 'source': 'fitbit', 'hrv_ms': 45, 'steps': 8000},
      {'date': '2026-10-14', 'source': 'oura', 'readiness_score': 82},
    ]);

    test('latest skips days without the measure', () {
      expect(week.latest('hrv_ms'), 45);
      expect(week.latest('readiness_score'), 82);
      expect(week.latest('sleep_minutes'), isNull);
    });

    test('names every source once', () {
      expect(week.sources, 'Oura and Fitbit');
      expect(const BodyWeek([]).sources, isNull);
    });

    test('averages only the days that have the measure', () {
      expect(week.average('hrv_ms'), 43);
    });
  });
}
