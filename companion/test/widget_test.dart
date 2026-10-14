import 'package:beats_companion/screens/pairing_screen.dart';
import 'package:beats_companion/theme/sky.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget app() => MaterialApp(
      theme: buildSkyTheme(SkyPalette.afternoon, Brightness.light),
      home: PairingScreen(onPaired: () {}),
    );

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('Pairing screen asks for a code', (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();

    expect(find.text('Pair this Mac'), findsOneWidget);
    expect(find.text('Pair'), findsOneWidget);
    expect(find.byKey(const Key('pairing-code')), findsOneWidget);
  });

  testWidgets('Pairing rejects a short code', (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();

    await tester.enterText(find.byKey(const Key('pairing-code')), 'AB');
    await tester.tap(find.text('Pair'));
    await tester.pump();

    expect(find.text('Enter a 6-character code'), findsOneWidget);
  });
}
