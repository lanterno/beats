import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:beats_companion/screens/pairing_screen.dart';

void main() {
  testWidgets('Pairing screen renders correctly', (WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      home: PairingScreen(onPaired: () {}),
    ));
    // Drain StaggeredEntrance timers and entrance animation.
    // Embers run forever, so pumpAndSettle would hang — pump enough to
    // drain the StaggeredEntrance entries instead (longest delay ~220ms,
    // duration 400ms → 700ms is plenty).
    await tester.pump(const Duration(milliseconds: 700));

    expect(find.text('Beats'), findsOneWidget);
    expect(find.text('Pair'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(3)); // API URL + Web UI URL + code
  });

  testWidgets('Pairing rejects short code', (WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      home: PairingScreen(onPaired: () {}),
    ));
    // Embers run forever, so pumpAndSettle would hang — pump enough to
    // drain the StaggeredEntrance entries instead (longest delay ~220ms,
    // duration 400ms → 700ms is plenty).
    await tester.pump(const Duration(milliseconds: 700));

    // Enter a short code and tap Pair
    final codeField = find.byType(TextField).last;
    await tester.enterText(codeField, 'AB');
    await tester.tap(find.text('Pair'));
    await tester.pump();

    expect(find.text('Enter a 6-character code'), findsOneWidget);
  });
}
