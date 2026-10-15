import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'screens/pairing_screen.dart';
import 'screens/shell.dart';
import 'screens/timer_actions.dart';
import 'popover/popover_app.dart';
import 'services/api_client.dart';
import 'services/notification_poller.dart';
import 'services/notifications.dart';
import 'services/sample_api.dart';
import 'services/status_menu.dart';
import 'services/token_storage.dart';
import 'services/tray_service.dart';
import 'package:window_manager/window_manager.dart';
import 'brand.dart';
import 'state/hour.dart';
import 'state/idle_watcher.dart';
import 'state/timer_controller.dart';
import 'state/week_controller.dart';
import 'theme/sky.dart';
import 'ui/kit.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  if (Platform.isMacOS) {
    // The sky runs under a hidden title bar; the traffic lights stay and sit
    // in the sidebar's top corner. A debug build opened with LIFEPETE_PHONE=1
    // is a phone-sized window, to look at the phone layout without a device;
    // LIFEPETE_PHONE=store is 9:16 (1080×1920 on a Retina screen), the shape
    // Google Play wants its screenshots in. Neither shows the traffic lights.
    final phone = kDebugMode ? Platform.environment['LIFEPETE_PHONE'] : null;
    await windowManager.waitUntilReadyToShow(
      WindowOptions(
        title: appName,
        size: switch (phone) {
          '1' => const Size(390, 844),
          'store' => const Size(540, 960),
          _ => const Size(1180, 820),
        },
        minimumSize: phone == null ? const Size(880, 620) : const Size(360, 640),
        titleBarStyle: TitleBarStyle.hidden,
        windowButtonVisibility: phone == null,
      ),
      () async {
        await windowManager.show();
        await windowManager.focus();
      },
    );
  }
  final hour = HourController();
  await hour.load();
  // A phone-sized debug window draws as Android where the theme decides
  // (Focus's Stop button instead of keyboard hints, scrolling, transitions),
  // so a screenshot of it shows what a phone would. Only the theme: the Mac
  // menu bar and window code still know they run on a Mac.
  final phone = kDebugMode && Platform.environment['LIFEPETE_PHONE'] != null;
  runApp(CompanionApp(hour: hour, platform: phone ? TargetPlatform.android : null));
}

/// The menu bar popover's engine starts here (StatusItemController.swift).
@pragma('vm:entry-point')
Future<void> popoverMain() => runPopover();

class CompanionApp extends StatelessWidget {
  final HourController hour;

  /// The platform the theme draws for, when not the one it runs on.
  final TargetPlatform? platform;

  const CompanionApp({super.key, required this.hour, this.platform});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder(
      valueListenable: hour,
      builder: (context, _, _) => MaterialApp(
        title: appName,
        debugShowCheckedModeBanner: false,
        theme: buildSkyTheme(SkyPalette.afternoon, Brightness.light).copyWith(platform: platform),
        darkTheme: buildSkyTheme(SkyPalette.dusk, Brightness.dark).copyWith(platform: platform),
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

  /// Looking around on SampleApi rather than a paired account: nothing is
  /// stored, no notifications, and the pairing screen is one tap away.
  bool _sample = false;
  ApiClient? _client;
  TimerController? _timer;
  WeekController? _week;
  IdleWatcher? _idle;
  TrayService? _tray;
  NotificationPoller? _poller;
  StreamSubscription<NotificationTap>? _notificationTaps;

  @override
  void initState() {
    super.initState();
    _checkPairing();
  }

  bool _routed = false;

  void _debugRoute() {
    if (_routed) return;
    _routed = true;
    _debugRouteOnce(_window);
  }

  Future<void> _checkPairing() async {
    if (_debugSample() != null) {
      // Straight into sample data, never touching the keychain: a debug
      // build shares it with the installed app.
      setState(() {
        _sample = true;
        _paired = true;
        _loading = false;
        _connect(SampleApi());
      });
      return;
    }
    String? token;
    try {
      token = await _storage.loadToken();
      if (token != null) {
        final apiUrl = await _storage.loadApiUrl();
        _connect(ApiClient(baseUrl: apiUrl, deviceToken: token));
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
    _idle = IdleWatcher(_timer!);
    if (Platform.isMacOS) _idle!.start();
    _tray = TrayService(
      client: client,
      timer: _timer!,
      onShowWindow: () async {
        await windowManager.show();
        await windowManager.focus();
      },
    )..init();
    StatusMenu.listen(
      show: (section, route) => _window.currentState?.showByName(section: section, route: route),
      refresh: () => _timer?.refresh(),
    );
  }

  void _disconnect() {
    _tray?.dispose();
    _tray = null;
    _idle?.dispose();
    _idle = null;
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
      if (tap.actionId == kTakeOffAwayActionId) {
        _idle?.takeOff();
        return;
      }
      if (tap.payload == 'away') {
        _window.currentState?.show(Section.today);
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

  void _onSample() {
    setState(() {
      _sample = true;
      _paired = true;
      _connect(SampleApi());
    });
  }

  void _onUnpaired() {
    _sample = false;
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
      return PairingScreen(onPaired: _onPaired, onSample: _onSample);
    }

    _debugRoute();
    return MainWindow(
      key: _window,
      initial: _debugSection(),
      client: _client!,
      timer: _timer!,
      week: _week!,
      idle: _idle!,
      hour: widget.hour,
      onUnpaired: _onUnpaired,
      sample: _sample && _debugSample() != 'quiet',
    );
  }
}

/// In a debug build, `LIFEPETE_ROUTE=settings` (or `focus`) opens that
/// over the window once it is up.
void _debugRouteOnce(GlobalKey<MainWindowState> window) {
  if (!kDebugMode) return;
  final route = Platform.environment['LIFEPETE_ROUTE'];
  if (route == null) return;
  WidgetsBinding.instance.addPostFrameCallback((_) => window.currentState?.showByName(route: route));
}

/// In a debug build, `LIFEPETE_SAMPLE=1` opens on sample data (`quiet`
/// leaves out the sample banner, for the store's screenshots).
String? _debugSample() => kDebugMode ? Platform.environment['LIFEPETE_SAMPLE'] : null;

/// In a debug build, `LIFEPETE_SECTION=flow` (today, flow, coach, body)
/// opens on that place, so each screen can be looked at without clicking:
/// `open --env LIFEPETE_SECTION=flow build/macos/…/beats_companion.app`.
Section _debugSection() {
  if (!kDebugMode) return Section.today;
  final name = Platform.environment['LIFEPETE_SECTION'];
  return Section.values.where((s) => s.name == name).firstOrNull ?? Section.today;
}
