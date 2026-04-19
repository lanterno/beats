import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'screens/pairing_screen.dart';
import 'screens/timer_screen.dart';
import 'services/api_client.dart';
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
          seedColor: const Color(0xFFD4952A),
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
  ApiClient? _client;
  int _currentTab = 0;

  @override
  void initState() {
    super.initState();
    _checkPairing();
  }

  Future<void> _checkPairing() async {
    final token = await _storage.loadToken();
    if (token != null) {
      final apiUrl = await _storage.loadApiUrl();
      _client = ApiClient(baseUrl: apiUrl, deviceToken: token);
    }
    setState(() {
      _paired = token != null;
      _loading = false;
    });
  }

  void _onPaired() async {
    final token = await _storage.loadToken();
    final apiUrl = await _storage.loadApiUrl();
    setState(() {
      _paired = true;
      _client = ApiClient(baseUrl: apiUrl, deviceToken: token);
    });
  }

  void _onUnpaired() {
    setState(() {
      _paired = false;
      _client = null;
      _currentTab = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (!_paired || _client == null) {
      return PairingScreen(onPaired: _onPaired);
    }

    return Scaffold(
      body: IndexedStack(
        index: _currentTab,
        children: [
          TimerScreen(client: _client!),
          HomeScreen(onUnpaired: _onUnpaired),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentTab,
        onDestinationSelected: (i) => setState(() => _currentTab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.timer), label: 'Timer'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}
