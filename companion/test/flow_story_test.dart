// flow_story reads one-minute flow windows into what the Flow screen says.
// The cases are the inputs where a reading goes wrong: gaps between
// windows, ties, an empty day, a stretch still running at the end of the
// data, and percentages that must still add to 100 after rounding.

import 'package:beats_companion/services/flow_story.dart';
import 'package:flutter_test/flutter_test.dart';

DateTime t(int h, int m) => DateTime(2026, 10, 14, h, m);

FlowSample s(int h, int m, double score, {String? repo, String? lang, String? app}) => FlowSample(
      start: t(h, m),
      end: t(h, m).add(const Duration(minutes: 1)),
      score: score,
      repo: repo,
      language: lang,
      bundle: app,
    );

/// [n] consecutive one-minute windows from h:m at [score].
List<FlowSample> run(int h, int m, int n, double score, {String? repo}) =>
    [for (var i = 0; i < n; i++) s(h, m + i, score, repo: repo)];

void main() {
  group('FlowSample.fromJson', () {
    test('reads the API row, defaulting a missing end to one minute', () {
      final sample = FlowSample.fromJson({
        'window_start': '2026-10-14T09:20:00Z',
        'flow_score': 0.8,
        'editor_repo': 'northwind-api',
        'editor_language': '',
      })!;
      expect(sample.end.difference(sample.start), const Duration(minutes: 1));
      expect(sample.repo, 'northwind-api');
      expect(sample.language, isNull);
    });

    test('drops rows without a start or a score and clamps the score', () {
      expect(FlowSample.fromJson({'flow_score': 0.5}), isNull);
      expect(FlowSample.fromJson({'window_start': '2026-10-14T09:20:00Z'}), isNull);
      expect(FlowSample.fromJson({'window_start': '2026-10-14T09:20:00Z', 'flow_score': 1.4})!.score, 1.0);
    });
  });

  group('flowBars', () {
    test('an empty day has no bars', () {
      expect(flowBars(const []), isEmpty);
    });

    test('spans whole hours from the first window to the last', () {
      final bars = flowBars([s(9, 20, 0.5), s(10, 59, 0.5)]);
      expect(bars.first.start, t(9, 0));
      expect(bars.last.end, t(11, 0));
      expect(bars.length, 24);
    });

    test('a last window exactly on the hour gets that hour', () {
      final bars = flowBars([s(9, 0, 0.5), s(10, 0, 0.5)]);
      expect(bars.last.end, t(11, 0));
    });

    test('averages each five minutes and leaves gaps empty', () {
      final bars = flowBars([s(9, 0, 0.6), s(9, 4, 0.8), s(9, 12, 0.9)]);
      expect(bars[0].score, closeTo(0.7, 1e-9));
      expect(bars[0].count, 2);
      expect(bars[1].score, isNull);
      expect(bars[2].score, 0.9);
    });

    test('names the most common repo, the first seen winning a tie', () {
      final bars = flowBars([
        s(9, 0, 0.5, repo: 'a', app: 'com.microsoft.VSCode'),
        s(9, 1, 0.5, repo: 'b'),
        s(9, 2, 0.5, repo: 'b'),
        s(9, 5, 0.5, repo: 'c'),
        s(9, 6, 0.5, repo: 'd'),
      ]);
      expect(bars[0].repo, 'b');
      expect(bars[0].bundle, 'com.microsoft.VSCode');
      expect(bars[1].repo, 'c');
    });
  });

  group('bestStretch', () {
    test('is null when nothing reaches the flow line', () {
      expect(bestStretch(run(9, 0, 30, 0.69)), isNull);
      expect(bestStretch(const []), isNull);
    });

    test('takes the longest run, ending at its last window\'s end', () {
      final samples = [...run(9, 0, 10, 0.8), s(9, 10, 0.3), ...run(9, 20, 75, 0.75, repo: 'northwind-api')];
      final best = bestStretch(samples)!;
      expect(best.start, t(9, 20));
      expect(best.end, t(10, 35));
      expect(best.repo, 'northwind-api');
    });

    test('a short gap does not break a run; a longer one does', () {
      final bridged = [...run(9, 0, 5, 0.8), ...run(9, 7, 5, 0.8)];
      expect(bestStretch(bridged)!.length, const Duration(minutes: 12));
      final broken = [...run(9, 0, 5, 0.8), ...run(9, 10, 4, 0.8)];
      expect(bestStretch(broken)!.end, t(9, 5));
    });

    test('a tie in length goes to the higher average, then the earlier', () {
      final samples = [...run(9, 0, 10, 0.75), s(9, 10, 0.1), ...run(10, 0, 10, 0.9)];
      expect(bestStretch(samples)!.start, t(10, 0));
      final even = [...run(9, 0, 10, 0.8), s(9, 10, 0.1), ...run(10, 0, 10, 0.8)];
      expect(bestStretch(even)!.start, t(9, 0));
    });

    test('a run still going at the end of the data counts', () {
      final samples = [...run(9, 0, 5, 0.8), s(9, 5, 0.2), ...run(17, 0, 30, 0.85)];
      expect(bestStretch(samples)!.end, t(17, 30));
    });
  });

  group('flowHeadline', () {
    test('names the best stretch and its repo', () {
      expect(
        flowHeadline(run(9, 20, 75, 0.8, repo: 'northwind-api'), today: true),
        'Your best stretch was 9:20 to 10:35, in northwind-api.',
      );
    });

    test('falls back to the peak minute when no stretch lasted', () {
      final samples = [...run(9, 0, 3, 0.8), s(10, 40, 0.95), ...run(11, 0, 20, 0.4)];
      expect(
        flowHeadline(samples, today: false),
        'No long stretch of flow that day. Your best minute came at 10:40.',
      );
    });
  });

  test('peakSample takes the earliest of equal peaks', () {
    expect(peakSample([s(9, 0, 0.9), s(10, 0, 0.9), s(11, 0, 0.5)])!.start, t(9, 0));
  });

  test('timeInFlow and timeInFlowBy count only minutes on the line', () {
    final samples = [...run(9, 0, 10, 0.8, repo: 'a'), ...run(10, 0, 5, 0.5, repo: 'a'), ...run(11, 0, 3, 0.7)];
    expect(timeInFlow(samples), const Duration(minutes: 13));
    expect(timeInFlowBy(samples, (x) => x.repo), {'a': const Duration(minutes: 10)});
  });

  group('comparedWithYesterday', () {
    test('says points above, below or the same', () {
      expect(comparedWithYesterday(71, 64), "7 points above yesterday's 64.");
      expect(comparedWithYesterday(63, 64), "1 point below yesterday's 64.");
      expect(comparedWithYesterday(64, 64), 'The same average as yesterday.');
      expect(comparedWithYesterday(64, null), isNull);
    });
  });

  group('categoryShares', () {
    test('three equal thirds still add up to 100', () {
      final shares = categoryShares({'coding': 1, 'browser': 1, 'design': 1});
      expect(shares.fold<int>(0, (a, s) => a + s.$2), 100);
      expect(shares.map((s) => s.$2), containsAll([34, 33]));
    });

    test('biggest first, and empty or vanishing categories left out', () {
      final shares = categoryShares({'coding': 580, 'browser': 170, 'other': 0, 'social': 1, 'design': 249});
      expect(shares.first, ('coding', 58));
      expect(shares.map((s) => s.$1), isNot(contains('other')));
      expect(shares.map((s) => s.$1), isNot(contains('social')));
      expect(shares.fold<int>(0, (a, s) => a + s.$2), 100);
    });

    test('no samples is no shares', () {
      expect(categoryShares({}), isEmpty);
      expect(categoryShares({'coding': 0}), isEmpty);
    });
  });
}
