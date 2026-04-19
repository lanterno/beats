import 'package:flutter_test/flutter_test.dart';
import 'package:beats_companion/main.dart';

void main() {
  testWidgets('App starts and shows pairing screen', (WidgetTester tester) async {
    await tester.pumpWidget(const BeatsCompanionApp());
    await tester.pumpAndSettle();

    // Should show the pairing screen when no token is stored
    expect(find.text('Pair with Beats'), findsOneWidget);
  });
}
