import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../screens/palette.dart';
import '../screens/timer_actions.dart';
import '../services/api_client.dart';
import '../services/time_format.dart';
import '../services/token_storage.dart';
import '../state/hour.dart';
import '../state/timer_controller.dart';
import '../state/week_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';

/// The menu bar popover: a second Flutter engine started by
/// `StatusItemController.swift` on the first click, through `popoverMain`
/// in main.dart. It reads the same token and API as the window and keeps
/// its own timer state; the two tell each other over the native side when
/// either changes the timer.
Future<void> runPopover() async {
  WidgetsFlutterBinding.ensureInitialized();
  final hour = HourController();
  await hour.load();
  runApp(PopoverApp(hour: hour));
}

const _channel = MethodChannel('companion/popover');

class PopoverApp extends StatefulWidget {
  final HourController hour;
  const PopoverApp({super.key, required this.hour});

  @override
  State<PopoverApp> createState() => _PopoverAppState();
}

class _PopoverAppState extends State<PopoverApp> {
  TimerController? _timer;
  WeekController? _week;
  bool _loaded = false;
  String _mode = 'panel';
  String _timerKey = '';

  @override
  void initState() {
    super.initState();
    _channel.setMethodCallHandler(_onCall);
    _connect();
  }

  Future<void> _connect() async {
    final storage = TokenStorage();
    final token = await storage.loadToken();
    final apiUrl = await storage.loadApiUrl();
    if (token != null && apiUrl != null) {
      final client = ApiClient(baseUrl: apiUrl, deviceToken: token);
      final timer = TimerController(client)..start();
      timer.addListener(_onTimer);
      _timer = timer;
      _week = WeekController(client, timer)..start();
    }
    if (mounted) setState(() => _loaded = true);
  }

  /// Tells the window (through the native side) when this popover changed
  /// the timer, so it doesn't wait for its next poll.
  void _onTimer() {
    final t = _timer!;
    final key = '${t.current?.id}@${t.since}';
    if (_timerKey.isNotEmpty && key != _timerKey) {
      _channel.invokeMethod('timer.changed');
    }
    _timerKey = key;
  }

  Future<void> _onCall(MethodCall call) async {
    switch (call.method) {
      case 'popover.show':
        final mode = (call.arguments as Map?)?['mode'] as String? ?? 'panel';
        // Settings live in the window's engine; pick up a changed hour.
        await (await SharedPreferences.getInstance()).reload();
        await widget.hour.load();
        if (_timer == null) await _connect();
        unawaited(_timer?.refresh());
        if (mounted) setState(() => _mode = mode);
      case 'popover.hidden':
        if (mounted) setState(() => _mode = 'panel');
      case 'timer.refresh':
        unawaited(_timer?.refresh());
    }
  }

  @override
  void dispose() {
    _timer?.removeListener(_onTimer);
    _week?.dispose();
    _timer?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder(
      valueListenable: widget.hour,
      builder: (context, _, _) => MaterialApp(
        title: appName,
        debugShowCheckedModeBanner: false,
        theme: buildSkyTheme(SkyPalette.afternoon, Brightness.light),
        darkTheme: buildSkyTheme(SkyPalette.dusk, Brightness.dark),
        themeMode: widget.hour.themeMode,
        home: Builder(builder: (context) {
          final p = context.sky;
          final timer = _timer;
          Widget body;
          if (!_loaded) {
            body = const Center(child: CircularProgressIndicator());
          } else if (timer == null) {
            body = _NotPaired();
          } else if (_mode == 'palette') {
            body = Padding(
              padding: const EdgeInsets.all(10),
              child: QuickStartPalette(
                host: context,
                timer: timer,
                onDone: () => _channel.invokeMethod('popover.close'),
                actions: [
                  PaletteAction('Open $appName', Icons.open_in_new_rounded, () => _open()),
                  PaletteAction('Focus mode', Icons.fullscreen_rounded, () => _open(route: 'focus')),
                ],
              ),
            );
          } else {
            body = _Panel(timer: timer, week: _week!, onOpen: _open);
          }
          return Scaffold(backgroundColor: p.panel.withValues(alpha: 1), body: body);
        }),
      ),
    );
  }

  void _open({String? section, String? route}) {
    _channel.invokeMethod('app.open', {'section': ?section, 'route': ?route});
  }
}

class _NotPaired extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Center(
        child: EmptyNote(
          icon: Icons.link_rounded,
          title: 'Pair $appName first',
          body: 'Open the window and type the code from the web.',
          action: SkyButton(
            label: 'Open $appName',
            kind: SkyButtonKind.primary,
            onPressed: () => _channel.invokeMethod('app.open', const <String, Object>{}),
          ),
        ),
      );
}

class _Panel extends StatelessWidget {
  final TimerController timer;
  final WeekController week;
  final void Function({String? section, String? route}) onOpen;
  const _Panel({required this.timer, required this.week, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return ListenableBuilder(
      listenable: Listenable.merge([timer, week]),
      builder: (context, _) {
        final current = timer.current;
        return Padding(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (current != null) ..._running(context, current) else ..._idle(context),
            const SizedBox(height: 14),
            _progress(context),
            const SizedBox(height: 10),
            Expanded(child: _projects(context)),
            Divider(height: 1, color: p.hairline),
            const SizedBox(height: 4),
            Row(children: [
              LinkButton(label: 'Focus mode', onPressed: () => onOpen(route: 'focus')),
              LinkButton(label: 'Open window', onPressed: () => onOpen()),
              const Spacer(),
              IconButton(
                tooltip: 'Settings',
                onPressed: () => onOpen(route: 'settings'),
                icon: Icon(Icons.settings_outlined, size: 18, color: p.inkMuted),
              ),
            ]),
          ]),
        );
      },
    );
  }

  List<Widget> _running(BuildContext context, Project current) {
    final p = context.sky;
    return [
      Row(children: [
        ProjectDot(color: current.color),
        const SizedBox(width: 8),
        Flexible(
          child: Text(current.name,
              overflow: TextOverflow.ellipsis, style: SkyType.body(15, weight: FontWeight.w700)),
        ),
        const SizedBox(width: 8),
        Text(current.kindLabel, style: SkyType.body(13).copyWith(color: p.inkMuted)),
      ]),
      const SizedBox(height: 10),
      ValueListenableBuilder(
        valueListenable: timer.now,
        builder: (context, _, _) => FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(formatClock(timer.elapsed), style: SkyType.figure(54)),
        ),
      ),
      const SizedBox(height: 6),
      Text('since ${formatTimeOfDay(timer.since!)}', style: SkyType.body(13).copyWith(color: p.inkOnSky)),
      const SizedBox(height: 14),
      SkyButton(
        label: 'Stop',
        icon: Icons.stop_rounded,
        kind: SkyButtonKind.primary,
        large: true,
        onPressed: () => TimerActions.stop(context, timer),
      ),
    ];
  }

  List<Widget> _idle(BuildContext context) {
    final p = context.sky;
    final stopped = timer.lastStopped;
    final fresh = stopped != null && DateTime.now().difference(stopped.at) < const Duration(minutes: 10);
    return [
      if (fresh) ...[
        Container(
          padding: const EdgeInsets.fromLTRB(12, 2, 2, 2),
          decoration: BoxDecoration(
            color: p.leaf.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Row(children: [
            Icon(Icons.check_rounded, size: 16, color: p.leafInk),
            const SizedBox(width: 8),
            Expanded(
              child: Text('${formatDuration(stopped.length)} logged to ${stopped.project.name}',
                  style: SkyType.body(13).copyWith(color: p.leafInk)),
            ),
            LinkButton(
              label: 'Undo',
              bold: true,
              color: p.leafInk,
              onPressed: () => TimerActions.undo(ScaffoldMessenger.of(context), timer),
            ),
          ]),
        ),
        const SizedBox(height: 12),
      ],
      Text('Nothing running', style: SkyType.display(22)),
      const SizedBox(height: 4),
      Text('Pick a project below, or press ⌃⌥T anywhere to type one.',
          style: SkyType.body(13).copyWith(color: p.inkMuted)),
      Align(
        alignment: Alignment.centerLeft,
        child: LinkButton(label: 'Log time you forgot…', onPressed: () => onOpen(route: 'log')),
      ),
    ];
  }

  Widget _progress(BuildContext context) {
    final p = context.sky;
    return ValueListenableBuilder(
      valueListenable: timer.now,
      builder: (context, now, _) {
        final today = week.todayMinutes(now);
        final target = week.dailyTargetMinutes(now);
        // Which project anchors the week can change until it has all arrived.
        final anchor = week.complete ? week.anchor : null;
        Widget line(String label, String value, String? of, double fraction, Color color) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  Text(label, style: SkyType.body(13)),
                  const Spacer(),
                  Text(value, style: SkyType.figure(13, weight: FontWeight.w700)),
                  if (of != null) Text(' / $of', style: SkyType.body(13).copyWith(color: p.inkMuted)),
                ]),
                const SizedBox(height: 6),
                ProgressBar(fraction: fraction, color: color),
              ]),
            );
        return Container(
          padding: const EdgeInsets.fromLTRB(14, 6, 14, 6),
          decoration: BoxDecoration(color: p.wash, borderRadius: BorderRadius.circular(16)),
          child: Column(children: [
            line('Today', formatMinutes(today), target == null ? null : formatMinutes(target),
                target == null || target == 0 ? 0 : today / target, p.sun),
            if (anchor != null)
              line('Week · ${anchor.project.name}', formatMinutes((anchor.worked * 60).round()),
                  formatMinutes((anchor.target! * 60).round()), anchor.worked / anchor.target!, anchor.project.color),
          ]),
        );
      },
    );
  }

  Widget _projects(BuildContext context) {
    final p = context.sky;
    final projects = timer.recentFirst.where((x) => x.id != timer.current?.id).take(6).toList();
    return ListView(padding: EdgeInsets.zero, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
        child: Text(timer.running ? 'Switch to' : 'Start',
            style: SkyType.body(12, weight: FontWeight.w700).copyWith(color: p.inkMuted)),
      ),
      for (final project in projects)
        InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => TimerActions.start(context, timer, project),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
            child: Row(children: [
              Icon(Icons.play_arrow_rounded, size: 18, color: project.color),
              const SizedBox(width: 8),
              Expanded(child: Text(project.name, overflow: TextOverflow.ellipsis, style: SkyType.body(14))),
              if (week.weekOf(project.id) != null && week.weekOf(project.id)!.worked > 0)
                Text(formatMinutes((week.weekOf(project.id)!.worked * 60).round()),
                    style: SkyType.figure(12, weight: FontWeight.w500).copyWith(color: p.inkMuted)),
            ]),
          ),
        ),
    ]);
  }
}
