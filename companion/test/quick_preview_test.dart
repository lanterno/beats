import 'package:beats_companion/services/quick_preview.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime(2026, 10, 15, 11, 5);
  final since = DateTime(2026, 10, 15, 9, 41);

  group('previewStart', () {
    test('nothing running starts now, with nothing more to say', () {
      final p = previewStart(project: 'Studio Kite', now: now);
      expect(p.title, 'Start Studio Kite');
      expect(p.detail, isNull);
    });

    test('nothing running, from a time, says how long ago that was', () {
      final p = previewStart(project: 'Spanish', now: now, at: DateTime(2026, 10, 15, 10, 40));
      expect(p.title, 'Start Spanish from 10:40');
      expect(p.detail, 'Starts 25m ago');
    });

    test('a switch now names what stops and how long it ran', () {
      final p = previewStart(project: 'Studio Kite', now: now, running: 'Northwind', since: since);
      expect(p.title, 'Switch to Studio Kite');
      expect(p.detail, 'Stops Northwind (1h 24m)');
    });

    test('a switch from a time stops the running one then, not now', () {
      final p = previewStart(
        project: 'Studio Kite',
        now: now,
        at: DateTime(2026, 10, 15, 11),
        running: 'Northwind',
        since: since,
      );
      expect(p.title, 'Switch to Studio Kite from 11:00');
      expect(p.detail, 'Stops Northwind at 11:00 (1h 19m) · Studio Kite starts 5m ago');
    });

    test('the running project again, from a time, is a restart', () {
      final p = previewStart(
        project: 'Northwind',
        now: now,
        at: DateTime(2026, 10, 15, 10),
        running: 'Northwind',
        since: since,
        same: true,
      );
      expect(p.title, 'Restart Northwind from 10:00');
    });

    test('two projects that share a name still switch', () {
      final p = previewStart(project: 'Admin', now: now, running: 'Admin', since: since);
      expect(p.title, 'Switch to Admin');
    });

    test('a start under a minute ago reads as now', () {
      final p = previewStart(project: 'Spanish', now: now, at: now.subtract(const Duration(seconds: 20)));
      expect(p.detail, 'Starts now');
    });
  });

  group('previewStop', () {
    test('now logs everything since the start', () {
      final p = previewStop(running: 'Northwind', since: since, now: now);
      expect(p.title, 'Stop Northwind');
      expect(p.detail, 'Logs 1h 24m');
    });

    test('at a time logs up to then', () {
      final p = previewStop(running: 'Northwind', since: since, now: now, at: DateTime(2026, 10, 15, 10, 50));
      expect(p.title, 'Stop Northwind at 10:50');
      expect(p.detail, 'Logs 1h 09m');
    });

    test('a UTC start and a local stop measure the same span', () {
      final p = previewStop(running: 'Northwind', since: since.toUtc(), now: now);
      expect(p.detail, 'Logs 1h 24m');
    });
  });
}
