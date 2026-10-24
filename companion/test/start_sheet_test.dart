// The phone's start sheet against a scripted API: what a tile, the typed
// field and the card's button each send. The sentence on the card is
// quick_preview_test's business; this is about which time reaches the API.

import 'package:beats_companion/screens/start_sheet.dart';
import 'package:beats_companion/services/api_client.dart';
import 'package:beats_companion/state/timer_controller.dart';
import 'package:beats_companion/state/week_controller.dart';
import 'package:beats_companion/theme/sky.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Api extends ApiClient {
  _Api() : super(baseUrl: 'http://test');

  final calls = <String>[];
  late Map<String, dynamic> status = {
    'isBeating': true,
    'project': projects.first,
    'since': DateTime.now().toUtc().subtract(const Duration(hours: 1)).toIso8601String(),
  };
  final projects = [
    {'id': 'p1', 'name': 'Northwind', 'color': '#4F8FD6', 'kind': 'day_job'},
    {'id': 'p2', 'name': 'Studio Kite', 'color': '#E07A5F', 'kind': 'freelance'},
  ];

  @override
  Future<Map<String, dynamic>> getTimerStatus() async => status;

  @override
  Future<List<Map<String, dynamic>>> getProjects() async => projects;

  @override
  Future<Map<String, dynamic>> startTimer(String projectId, {String? startTime}) async {
    calls.add('start $projectId $startTime');
    status = {'isBeating': true, 'project': projects.firstWhere((p) => p['id'] == projectId), 'since': startTime};
    return {};
  }

  @override
  Future<Map<String, dynamic>> stopTimer({String? stopTime}) async {
    calls.add('stop $stopTime');
    final beat = {'id': 'b1', 'project_id': (status['project'] as Map)['id'], 'start': status['since'], 'end': stopTime};
    status = {'isBeating': false};
    return beat;
  }
}

/// The timer that ticks while something runs, disposed when a test ends
/// (the binding refuses to end a test with its one-second tick pending).
late TimerController _timer;

void _test(String name, Future<void> Function(WidgetTester) body) => testWidgets(name, (tester) async {
      try {
        await body(tester);
      } finally {
        _timer.dispose();
      }
    });

Future<_Api> _open(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final api = _Api();
  final timer = _timer = TimerController(api);
  await timer.refresh();
  final week = WeekController(api, timer);
  await tester.pumpWidget(MaterialApp(
    theme: buildSkyTheme(SkyPalette.afternoon, Brightness.light),
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showStartSheet(context, timer: timer, week: week, onLog: () {}, onFocus: () {}),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return api;
}

/// The stop and the start a switch sends, which must share one instant.
(String, String) _switch(List<String> calls) {
  expect(calls, hasLength(2));
  final stop = calls[0].split(' ')[1], start = calls[1].split(' ')[2];
  return (stop, start);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  _test('a tile switches now', (tester) async {
    final api = await _open(tester);
    await tester.tap(find.text('Studio Kite'));
    await tester.pumpAndSettle();

    expect(api.calls.last, startsWith('start p2 '));
    final (stop, start) = _switch(api.calls);
    expect(stop, start);
    expect(find.text('Start or switch'), findsNothing); // the sheet closed
  });

  _test('a typed time reaches both halves of the switch', (tester) async {
    final api = await _open(tester);
    final before = DateTime.now();
    await tester.enterText(find.byType(TextField), 'kite 25m ago');
    await tester.pump();
    expect(find.text('Switch to Studio Kite from ${_hm(before.subtract(const Duration(minutes: 25)))}'),
        findsOneWidget);

    await tester.tap(find.text('Switch'));
    await tester.pumpAndSettle();

    final (stop, start) = _switch(api.calls);
    expect(stop, start);
    final at = DateTime.parse(start);
    expect(before.difference(at).inMinutes, inInclusiveRange(24, 25));
  });

  _test('a typed time also goes with a tile tapped after it', (tester) async {
    final api = await _open(tester);
    await tester.enterText(find.byType(TextField), 'kite 10m ago');
    await tester.pump();
    await tester.tap(find.text('Studio Kite'));
    await tester.pumpAndSettle();

    final (_, start) = _switch(api.calls);
    expect(DateTime.now().difference(DateTime.parse(start)).inMinutes, inInclusiveRange(9, 10));
  });

  _test('the running project\'s tile does nothing', (tester) async {
    final api = await _open(tester);
    await tester.tap(find.text('Northwind'));
    await tester.pumpAndSettle();

    expect(api.calls, isEmpty);
    expect(find.text('Start or switch'), findsOneWidget);
  });

  _test('stop with a time stops then', (tester) async {
    final api = await _open(tester);
    await tester.enterText(find.byType(TextField), 'stop 10m ago');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Stop'));
    await tester.pumpAndSettle();

    expect(api.calls, hasLength(1));
    final at = DateTime.parse(api.calls.single.split(' ')[1]);
    expect(DateTime.now().difference(at).inMinutes, inInclusiveRange(9, 10));
  });

  _test('a time still to come is refused, not sent', (tester) async {
    final api = await _open(tester);
    final later = DateTime.now().add(const Duration(minutes: 30));
    if (later.day != DateTime.now().day) return; // past 23:30 there is no later today
    await tester.enterText(find.byType(TextField), 'kite from ${_hm(later)}');
    await tester.pump();

    expect(find.textContaining('hasn\'t happened yet'), findsOneWidget);
    await tester.tap(find.text('Studio Kite'));
    await tester.pumpAndSettle();
    expect(api.calls, isEmpty);
  });
}

String _hm(DateTime t) => '${t.hour}:${t.minute.toString().padLeft(2, '0')}';
