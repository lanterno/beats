import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'screens/pairing_screen.dart';
import 'services/token_storage.dart';

void main() {
  runApp(const BeatsCompanionApp());
}

class BeatsCompanionApp extends StatelessWidget {
  const BeatsCompanionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Beats Companion',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFD4952A), // Beats ember accent
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const AppShell(),
    );
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final _storage = TokenStorage();
  bool _loading = true;
  bool _paired = false;

  @override
  void initState() {
    super.initState();
    _checkPairing();
  }

  Future<void> _checkPairing() async {
    final token = await _storage.loadToken();
    setState(() {
      _paired = token != null;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (!_paired) {
      return PairingScreen(
        onPaired: () => setState(() => _paired = true),
      );
    }

    return HomeScreen(
      onUnpaired: () => setState(() => _paired = false),
    );
  }
}
