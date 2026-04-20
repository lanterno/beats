import 'dart:ui';
import 'package:flutter/material.dart';
import 'screens/coach_screen.dart';
import 'screens/flow_screen.dart';
import 'screens/home_screen.dart';
import 'screens/intentions_screen.dart';
import 'screens/pairing_screen.dart';
import 'screens/timer_screen.dart';
import 'services/api_client.dart';
import 'services/token_storage.dart';
import 'theme/beats_theme.dart';

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
      theme: buildBeatsTheme(),
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
      return Scaffold(
        backgroundColor: BeatsColors.background,
        body: const Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    if (!_paired || _client == null) {
      return PairingScreen(onPaired: _onPaired);
    }

    return Scaffold(
      backgroundColor: BeatsColors.background,
      extendBody: true,
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        switchInCurve: Curves.easeOutCubic,
        switchOutCurve: Curves.easeInCubic,
        transitionBuilder: (child, animation) {
          return FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween(
                begin: const Offset(0, 0.02),
                end: Offset.zero,
              ).animate(animation),
              child: child,
            ),
          );
        },
        child: KeyedSubtree(
          key: ValueKey(_currentTab),
          child: _buildCurrentScreen(),
        ),
      ),
      bottomNavigationBar: _BeatsNavBar(
        currentIndex: _currentTab,
        onTap: (i) => setState(() => _currentTab = i),
      ),
    );
  }

  Widget _buildCurrentScreen() {
    switch (_currentTab) {
      case 0: return TimerScreen(client: _client!);
      case 1: return FlowScreen(client: _client!);
      case 2: return IntentionsScreen(client: _client!);
      case 3: return CoachScreen(client: _client!);
      case 4: return HomeScreen(onUnpaired: _onUnpaired);
      default: return TimerScreen(client: _client!);
    }
  }
}

/// Custom frosted-glass bottom navigation bar.
class _BeatsNavBar extends StatelessWidget {
  final int currentIndex;
  final ValueChanged<int> onTap;

  const _BeatsNavBar({required this.currentIndex, required this.onTap});

  static const _items = [
    (icon: Icons.timer_outlined, activeIcon: Icons.timer, label: 'Timer'),
    (icon: Icons.insights_outlined, activeIcon: Icons.insights, label: 'Flow'),
    (icon: Icons.checklist_outlined, activeIcon: Icons.checklist, label: 'Plan'),
    (icon: Icons.auto_awesome_outlined, activeIcon: Icons.auto_awesome, label: 'Coach'),
    (icon: Icons.tune_outlined, activeIcon: Icons.tune, label: 'Settings'),
  ];

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return ClipRRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          height: 56 + bottomPadding,
          padding: EdgeInsets.only(bottom: bottomPadding),
          decoration: BoxDecoration(
            color: BeatsColors.background.withValues(alpha: 0.85),
            border: Border(
              top: BorderSide(color: BeatsColors.border.withValues(alpha: 0.5)),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: List.generate(_items.length, (i) {
              final selected = i == currentIndex;
              final item = _items[i];

              return GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onTap(i),
                child: SizedBox(
                  width: 56,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      AnimatedScale(
                        scale: selected ? 1.1 : 1.0,
                        duration: const Duration(milliseconds: 200),
                        curve: Curves.easeOutBack,
                        child: Icon(
                          selected ? item.activeIcon : item.icon,
                          size: 22,
                          color: selected
                              ? BeatsColors.amber
                              : BeatsColors.textTertiary,
                        ),
                      ),
                      const SizedBox(height: 3),
                      // Glow dot indicator
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 250),
                        width: selected ? 4 : 0,
                        height: selected ? 4 : 0,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: BeatsColors.amber,
                          boxShadow: selected
                              ? [BoxShadow(color: BeatsColors.amberGlow, blurRadius: 6)]
                              : [],
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ),
        ),
      ),
    );
  }
}
