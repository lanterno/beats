import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:beats_companion/screens/pairing_screen.dart';

void main() {
  testWidgets('Pairing screen renders correctly', (WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      home: PairingScreen(onPaired: () {}),
    ));

    expect(find.text('Pair with Beats'), findsOneWidget);
    expect(find.text('Pair'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2)); // API URL + code
  });

  testWidgets('Pairing rejects short code', (WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      home: PairingScreen(onPaired: () {}),
    ));

    // Enter a short code and tap Pair
    final codeField = find.byType(TextField).last;
    await tester.enterText(codeField, 'AB');
    await tester.tap(find.text('Pair'));
    await tester.pump();

    expect(find.text('Enter a 6-character pairing code'), findsOneWidget);
  });
}
