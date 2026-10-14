import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'screens/pairing_screen.dart';
import 'screens/shell.dart';
import 'screens/timer_actions.dart';
import 'services/api_client.dart';
import 'services/notification_poller.dart';
import 'services/notifications.dart';
import 'services/token_storage.dart';
import 'services/tray_service.dart';
import 'package:window_manager/window_manager.dart';
import 'brand.dart';
import 'state/hour.dart';
import 'state/timer_controller.dart';
import 'state/week_controller.dart';
import 'theme/sky.dart';
import 'ui/kit.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  if (Platform.isMacOS) {
    // The sky runs under a hidden title bar; the traffic lights stay and sit
    // in the sidebar's top corner.
    await windowManager.waitUntilReadyToShow(
      const WindowOptions(
        title: appName,
        size: Size(1180, 820),
        minimumSize: Size(880, 620),
        titleBarStyle: TitleBarStyle.hidden,
      ),
      () async {
        await windowManager.show();
        await windowManager.focus();
      },
    );
  }
  final hour = HourController();
  await hour.load();
  runApp(CompanionApp(hour: hour));
}

class CompanionApp extends StatelessWidget {
  final HourController hour;
  const CompanionApp({super.key, required this.hour});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder(
      valueListenable: hour,
      builder: (context, _, _) => MaterialApp(
        title: appName,
        debugShowCheckedModeBanner: false,
        theme: buildSkyTheme(SkyPalette.afternoon, Brightness.light),
        darkTheme: buildSkyTheme(SkyPalette.dusk, Brightness.dark),
        themeMode: hour.themeMode,
        home: AppShell(hour: hour),
      ),
    );
  }
}

class AppShell extends StatefulWidget {
  final HourController hour;
  const AppShell({super.key, required this.hour});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final _storage = TokenStorage();
  final _window = GlobalKey<MainWindowState>();
  bool _loading = true;
  bool _paired = false;
  ApiClient? _client;
  TimerController? _timer;
  WeekController? _week;
  TrayService? _tray;
  NotificationPoller? _poller;
  StreamSubscription<NotificationTap>? _notificationTaps;

  @override
  void initState() {
    super.initState();
    _checkPairing();
  }

  Future<void> _checkPairing() async {
    String? token;
    try {
      token = await _storage.loadToken();
      if (token != null) {
        final apiUrl = await _storage.loadApiUrl();
        _connect(ApiClient(baseUrl: apiUrl, deviceToken: token));
        _tray = TrayService(
          client: _client!,
          onShowWindow: () async {
            await windowManager.show();
            await windowManager.focus();
          },
        );
        _tray!.init();
        await _initNotifications();
      }
    } catch (_) {
      // Anything from keychain read failures to tray init crashes lands here.
      // We surface the pairing screen rather than wedging on a spinner — the
      // user can re-pair to recover.
      token = null;
      _disconnect();
    }
    if (!mounted) return;
    setState(() {
      _paired = token != null && _client != null;
      _loading = false;
    });
  }

  /// Starts the shared timer and week for a paired client.
  void _connect(ApiClient client) {
    _client = client;
    _timer = TimerController(client)..start();
    _week = WeekController(client, _timer!)..start();
  }

  void _disconnect() {
    _week?.dispose();
    _timer?.dispose();
    _week = null;
    _timer = null;
    _client = null;
  }

  @override
  void dispose() {
    _poller?.stop();
    _notificationTaps?.cancel();
    _disconnect();
    super.dispose();
  }

  /// Initialize the notification stack and start the foreground poller.
  ///
  /// Tap routing:
  /// - The `Start` action button on an auto-timer notification fires the
  ///   `kStartAutoTimerActionId` actionId. We start the suggested project
  ///   (switching from whatever runs) without bringing a screen forward;
  ///   a confirmation lands on whatever screen the user is already on.
  /// - Body taps on any other notification (`brief`, plain `auto-timer:*`)
  ///   open the Coach.
  Future<void> _initNotifications() async {
    final svc = NotificationsService.instance;
    await svc.init();
    // Permission prompt is best surfaced from a Settings toggle, not on
    // first launch — but we ask once here so the very first run gets the
    // dialog instead of silently failing.
    unawaited(svc.requestPermissions());

    _notificationTaps = svc.taps.listen((tap) {
      if (!mounted) return;
      if (tap.actionId == kStartAutoTimerActionId) {
        _handleStartAutoTimerAction(tap.payload);
        return;
      }
      _window.currentState?.show(Section.coach);
    });

    final poller = NotificationPoller(
      client: _client!,
      notifications: svc,
    );
    _poller = poller;
    poller.start();
  }

  /// Honors the auto-timer "Start" action button without bringing the app
  /// forward (it can fire while the app is in the background).
  Future<void> _handleStartAutoTimerAction(String? payload) async {
    final parsed = parseAutoTimerPayload(payload);
    final timer = _timer;
    if (parsed == null || timer == null) return;
    await timer.refresh();
    final project = timer.projectById(parsed.projectId);
    if (project == null || !mounted) return;
    await TimerActions.start(context, timer, project);
  }

  void _onPaired() async {
    final token = await _storage.loadToken();
    final apiUrl = await _storage.loadApiUrl();
    setState(() {
      _paired = true;
      _connect(ApiClient(baseUrl: apiUrl, deviceToken: token));
    });
    await _initNotifications();
  }

  void _onUnpaired() {
    _poller?.stop();
    _poller = null;
    _notificationTaps?.cancel();
    _notificationTaps = null;
    setState(() {
      _paired = false;
      _disconnect();
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: Colors.transparent,
        body: SkyBackdrop(child: Center(child: CircularProgressIndicator())),
      );
    }

    if (!_paired || _client == null) {
      return PairingScreen(onPaired: _onPaired);
    }

    return MainWindow(
      key: _window,
      client: _client!,
      timer: _timer!,
      week: _week!,
      onUnpaired: _onUnpaired,
    );
  }
}
