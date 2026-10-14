import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:window_manager/window_manager.dart';

import '../services/api_client.dart';
import '../services/mac_ambient.dart';
import '../services/notifications.dart';
import '../services/settings_story.dart';
import '../services/token_storage.dart';
import '../state/hour.dart';
import '../state/prefs.dart';
import '../state/timer_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';

enum _Tab { general, notifications, connections, account }

extension on _Tab {
  String get label => switch (this) {
        _Tab.general => 'General',
        _Tab.notifications => 'Notifications',
        _Tab.connections => 'Connections',
        _Tab.account => 'Account',
      };

  IconData get icon => switch (this) {
        _Tab.general => Icons.tune_rounded,
        _Tab.notifications => Icons.notifications_none_rounded,
        _Tab.connections => Icons.link_rounded,
        _Tab.account => Icons.person_outline_rounded,
      };
}

/// Settings, pushed over the whole window from ⌘, or the sidebar's gear:
/// four tabs of grouped rows on the sky.
class SettingsScreen extends StatefulWidget {
  final ApiClient client;
  final TimerController timer;
  final HourController hour;
  final VoidCallback onUnpaired;

  const SettingsScreen({
    super.key,
    required this.client,
    required this.timer,
    required this.hour,
    required this.onUnpaired,
  });

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  _Tab _tab = _Tab.general;

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final topBar = Padding(
      padding: EdgeInsets.fromLTRB(20, Platform.isMacOS ? 30 : 16, 20, 8),
      child: Column(children: [
        Row(children: [
          RoundIconButton(
            icon: Icons.close_rounded,
            tooltip: 'Close',
            onPressed: () => Navigator.of(context).maybePop(),
          ),
          Expanded(
            child: Center(
              child: Semantics(header: true, child: Text('Settings', style: SkyType.display(20))),
            ),
          ),
          const SizedBox(width: 36),
        ]),
        const SizedBox(height: 14),
        Wrap(alignment: WrapAlignment.center, spacing: 6, runSpacing: 6, children: [
          for (final t in _Tab.values)
            Semantics(
              selected: t == _tab,
              button: true,
              child: TextButton(
                onPressed: () => setState(() => _tab = t),
                style: TextButton.styleFrom(
                  backgroundColor: t == _tab ? p.washStrong : Colors.transparent,
                  foregroundColor: p.ink,
                  minimumSize: const Size(100, 60),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                ),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Icon(t.icon, size: 22),
                  const SizedBox(height: 4),
                  Text(t.label,
                      style: SkyType.body(13, weight: t == _tab ? FontWeight.w700 : FontWeight.w400)),
                ]),
              ),
            ),
        ]),
      ]),
    );

    final body = switch (_tab) {
      _Tab.general => _GeneralTab(hour: widget.hour),
      _Tab.notifications => const _NotificationsTab(),
      _Tab.connections => _ConnectionsTab(client: widget.client),
      _Tab.account => _AccountTab(client: widget.client, onUnpaired: widget.onUnpaired),
    };

    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () => Navigator.of(context).maybePop(),
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: SkyBackdrop(
            child: Column(children: [
              Platform.isMacOS ? DragToMoveArea(child: topBar) : topBar,
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(24, 12, 24, 40),
                  children: [
                    Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 700),
                        child: KeyedSubtree(key: ValueKey(_tab), child: body),
                      ),
                    ),
                  ],
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

// ─── Building blocks ────────────────────────────────────────────────

/// A rounded panel of rows separated by hairlines.
class _Group extends StatelessWidget {
  final List<Widget> rows;
  const _Group(this.rows);

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Panel(
      radius: 22,
      padding: EdgeInsets.zero,
      child: Column(children: [
        for (var i = 0; i < rows.length; i++) ...[
          if (i > 0) Divider(height: 1, thickness: 1, color: p.hairline),
          rows[i],
        ],
      ]),
    );
  }
}

class _Row extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget? leading;
  final Widget? trailing;
  final Widget? below;

  const _Row({required this.title, this.subtitle, this.leading, this.trailing, this.below});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          if (leading != null) ...[leading!, const SizedBox(width: 14)],
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: SkyType.body(15)),
              if (subtitle != null) ...[
                const SizedBox(height: 2),
                Text(subtitle!, style: SkyType.body(13).copyWith(color: p.inkMuted)),
              ],
            ]),
          ),
          if (trailing != null) ...[const SizedBox(width: 16), trailing!],
        ]),
        if (below != null) ...[const SizedBox(height: 12), below!],
      ]),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(8, 18, 8, 8),
        child: Text(text,
            style: SkyType.body(13, weight: FontWeight.w700).copyWith(color: context.sky.inkOnSky)),
      );
}

// ─── General ────────────────────────────────────────────────────────

class _GeneralTab extends StatefulWidget {
  final HourController hour;
  const _GeneralTab({required this.hour});

  @override
  State<_GeneralTab> createState() => _GeneralTabState();
}

class _GeneralTabState extends State<_GeneralTab> {
  Prefs? _prefs;
  bool? _atLogin;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await Prefs.load();
    final atLogin = await MacAmbient.openAtLogin();
    if (!mounted) return;
    setState(() {
      _prefs = prefs;
      _atLogin = atLogin;
    });
  }

  Future<void> _setAtLogin(bool v) async {
    final before = _atLogin;
    setState(() => _atLogin = v);
    try {
      final now = await MacAmbient.setOpenAtLogin(v);
      if (mounted) setState(() => _atLogin = now);
    } catch (e) {
      if (!mounted) return;
      setState(() => _atLogin = before);
      final reason = e is PlatformException ? (e.message ?? e.code) : '$e';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('macOS said no: $reason')));
    }
  }

  Future<void> _setDock(bool v) async {
    await _prefs!.setBool(Prefs.showInDock, v);
    await MacAmbient.setDockVisible(v);
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final prefs = _prefs;
    if (prefs == null) return const SizedBox(height: 200);
    final mac = Platform.isMacOS;
    return ValueListenableBuilder(
      valueListenable: widget.hour,
      builder: (context, hour, _) => _Group([
        if (mac && _atLogin != null)
          _Row(
            title: 'Open at login',
            trailing: Switch.adaptive(value: _atLogin!, onChanged: _setAtLogin),
          ),
        if (mac)
          _Row(
            title: 'Show in the Dock',
            subtitle: 'Off keeps LifePete in the menu bar only',
            trailing: Switch.adaptive(value: prefs.dockVisible, onChanged: _setDock),
          ),
        if (mac)
          _Row(
            title: 'Menu bar shows',
            trailing: SegmentedPills<MenuBarShows>(
              options: const [
                (MenuBarShows.timeAndProject, 'Time and project'),
                (MenuBarShows.time, 'Time'),
                (MenuBarShows.icon, 'Icon'),
              ],
              value: prefs.menuBarShows,
              onChanged: (m) async {
                await prefs.setMenuBarShows(m);
                if (mounted) setState(() {});
              },
            ),
          ),
        if (mac)
          const _Row(
            title: 'Quick start shortcut',
            subtitle: 'Opens the palette from any app',
            trailing: Chip2('⌃⌥T', bold: true),
          ),
        _Row(
          title: 'Hour',
          trailing: SegmentedPills<Hour>(
            options: [
              (Hour.afternoon, 'Afternoon'),
              (Hour.dusk, 'Dusk'),
              (Hour.system, mac ? 'Follow macOS' : 'Follow system'),
            ],
            value: hour,
            onChanged: widget.hour.set,
          ),
        ),
      ]),
    );
  }
}

// ─── Notifications ──────────────────────────────────────────────────

class _NotificationsTab extends StatefulWidget {
  const _NotificationsTab();

  @override
  State<_NotificationsTab> createState() => _NotificationsTabState();
}

class _NotificationsTabState extends State<_NotificationsTab> {
  Prefs? _prefs;

  @override
  void initState() {
    super.initState();
    Prefs.load().then((p) {
      if (mounted) setState(() => _prefs = p);
    });
  }

  Future<void> _set(String key, bool v) async {
    await _prefs!.setBool(key, v);
    if (v) unawaited(NotificationsService.instance.requestPermissions());
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final prefs = _prefs;
    if (prefs == null) return const SizedBox(height: 200);
    final p = context.sky;
    Widget toggle(String key, bool value) =>
        Switch.adaptive(value: value, onChanged: (v) => _set(key, v));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _Group([
        _Row(
          title: 'Morning brief',
          subtitle: 'Your coach\'s note for the day',
          trailing: toggle(Prefs.notifyBrief, prefs.briefOn),
        ),
        _Row(
          title: 'Suggest a timer',
          subtitle: 'When your editor is on a project\'s repo and nothing is running',
          trailing: toggle(Prefs.notifySuggest, prefs.suggestOn),
        ),
        _Row(
          title: 'Drift nudges',
          subtitle: 'When another app has had you for a while',
          trailing: toggle(Prefs.notifyDrift, prefs.driftOn),
        ),
        _Row(
          title: 'Hold them while I\'m in flow',
          subtitle: 'Briefs and nudges wait until your flow drops below 70',
          trailing: toggle(Prefs.holdInFlow, prefs.holdingInFlow),
        ),
      ]),
      if (Platform.isMacOS)
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 10, 8, 0),
          child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
            Text('macOS decides whether LifePete may notify you.',
                style: SkyType.body(13).copyWith(color: p.inkOnSky)),
            LinkButton(
              label: 'Open System Settings',
              bold: true,
              color: p.sunInk,
              onPressed: () => launchUrl(
                Uri.parse('x-apple.systempreferences:com.apple.preference.notifications'),
              ),
            ),
          ]),
        ),
    ]);
  }
}

// ─── Connections ────────────────────────────────────────────────────

/// What a connection row knows: still asking, the answer, or why it failed.
class _Status {
  final bool loading;
  final bool connected;
  final String? detail;
  final bool newerServer;
  final String? error;

  const _Status.loading()
      : loading = true,
        connected = false,
        detail = null,
        newerServer = false,
        error = null;
  const _Status(this.connected, {this.detail})
      : loading = false,
        newerServer = false,
        error = null;
  _Status.failed(Object e)
      : loading = false,
        connected = false,
        detail = null,
        newerServer = needsNewerServer(e),
        error = shortError(e);
}

class _ConnectionsTab extends StatefulWidget {
  final ApiClient client;
  const _ConnectionsTab({required this.client});

  @override
  State<_ConnectionsTab> createState() => _ConnectionsTabState();
}

class _ConnectionsTabState extends State<_ConnectionsTab> {
  List<Map<String, dynamic>>? _recent;
  List<Map<String, dynamic>>? _today;
  _Status _oura = const _Status.loading();
  _Status _fitbit = const _Status.loading();
  final _pat = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadSignals();
    _loadHealth();
  }

  @override
  void dispose() {
    _pat.dispose();
    super.dispose();
  }

  Future<void> _loadSignals() async {
    final now = DateTime.now();
    final dayStart = DateTime(now.year, now.month, now.day);
    List<Map<String, dynamic>> recent = const [], today = const [];
    try {
      recent = await widget.client.getFlowWindows(
        now.toUtc().subtract(const Duration(minutes: 10)).toIso8601String(),
        now.toUtc().toIso8601String(),
      );
    } catch (_) {}
    try {
      today = await widget.client.getFlowWindows(
        dayStart.toUtc().toIso8601String(),
        now.toUtc().toIso8601String(),
      );
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _recent = recent;
      _today = today;
    });
  }

  Future<void> _loadHealth() async {
    _Status oura, fitbit;
    try {
      final s = await widget.client.getOuraStatus();
      oura = _Status(s['connected'] == true);
    } catch (e) {
      oura = _Status.failed(e);
    }
    try {
      final s = await widget.client.getFitbitStatus();
      fitbit = _Status(s['connected'] == true, detail: s['fitbit_user_id'] as String?);
    } catch (e) {
      fitbit = _Status.failed(e);
    }
    if (!mounted) return;
    setState(() {
      _oura = oura;
      _fitbit = fitbit;
    });
  }

  void _say(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _run(Future<void> Function() action, String failure) async {
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      _say('$failure: ${shortError(e)}');
    }
    await _loadHealth();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _connectOura() async {
    final token = _pat.text.trim();
    if (token.isEmpty) return;
    await _run(() async {
      await widget.client.connectOura(token);
      _pat.clear();
      _say('Oura connected');
    }, 'Couldn\'t connect Oura');
  }

  Future<void> _connectFitbit() async {
    final Uri? url;
    try {
      final raw = (await widget.client.getFitbitAuthUrl())['url'] as String?;
      url = raw == null || raw.isEmpty ? null : Uri.tryParse(raw);
    } catch (e) {
      _say('Couldn\'t start Fitbit sign-in: ${shortError(e)}');
      return;
    }
    if (url == null) {
      _say('Couldn\'t start Fitbit sign-in');
      return;
    }
    if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
      _say('Couldn\'t open the browser');
      return;
    }
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => _FitbitWaitDialog(client: widget.client),
    );
    await _loadHealth();
  }

  Widget _dot(Color color, {bool hollow = false}) => Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: hollow ? null : color,
          border: hollow ? Border.all(color: color, width: 2) : null,
        ),
      );

  Widget _healthRow({
    required String name,
    required _Status status,
    required Widget connectControl,
    required String connectedDetail,
    required VoidCallback onDisconnect,
    Widget? below,
  }) {
    final p = context.sky;
    if (status.loading) {
      return _Row(title: name, subtitle: 'Checking…', leading: _dot(p.inkMuted, hollow: true));
    }
    if (status.error != null) {
      return _Row(
        title: name,
        subtitle: status.newerServer ? 'Needs a newer server' : 'Couldn\'t check: ${status.error}',
        leading: _dot(p.persimmon, hollow: true),
      );
    }
    if (status.connected) {
      return _Row(
        title: name,
        subtitle: connectedDetail,
        leading: _dot(p.leaf),
        trailing: SkyButton(label: 'Disconnect', onPressed: _busy ? null : onDisconnect),
      );
    }
    return _Row(
      title: name,
      subtitle: 'Not connected',
      leading: _dot(p.inkMuted, hollow: true),
      trailing: below == null ? connectControl : null,
      below: below,
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final recent = _recent;
    final today = _today;
    final newest = recent == null ? null : newestWindowEnd(recent);
    final workspaces = today == null ? null : workspaceCount(today);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const _SectionLabel('On this Mac'),
      _Group([
        if (recent == null)
          _Row(title: 'Activity daemon (beatsd)', subtitle: 'Checking…', leading: _dot(p.inkMuted, hollow: true))
        else if (newest != null)
          _Row(
            title: 'Activity daemon (beatsd)',
            subtitle: 'Running · last signal ${signalAgo(newest, DateTime.now())}',
            leading: _dot(p.leaf),
          )
        else
          _Row(
            title: 'Activity daemon (beatsd)',
            subtitle: 'No signal in the last 10 minutes. Run `beatsd run`, '
                'or pair it from the web\'s Settings → Daemon.',
            leading: _dot(p.inkMuted, hollow: true),
          ),
        _Row(
          title: 'VS Code extension',
          subtitle: workspaces == null
              ? 'Checking…'
              : workspaces > 0
                  ? 'Sending from $workspaces workspace${workspaces == 1 ? '' : 's'}'
                  : 'Not seen today',
          leading: _dot(workspaces != null && workspaces > 0 ? p.leaf : p.inkMuted,
              hollow: !(workspaces != null && workspaces > 0)),
        ),
      ]),
      const _SectionLabel('Health'),
      _Group([
        _healthRow(
          name: 'Oura',
          status: _oura,
          connectedDetail: 'Connected',
          onDisconnect: () => _run(widget.client.disconnectOura, 'Couldn\'t disconnect Oura'),
          connectControl: const SizedBox.shrink(),
          below: Row(children: [
            Expanded(
              child: TextField(
                controller: _pat,
                obscureText: true,
                style: SkyType.body(14),
                decoration: const InputDecoration(hintText: 'Personal access token'),
                onSubmitted: (_) => _connectOura(),
              ),
            ),
            const SizedBox(width: 10),
            SkyButton(
              label: 'Connect',
              kind: SkyButtonKind.primary,
              onPressed: _busy ? null : _connectOura,
            ),
          ]),
        ),
        _healthRow(
          name: 'Fitbit',
          status: _fitbit,
          connectedDetail: _fitbit.detail == null ? 'Connected' : 'Connected as ${_fitbit.detail}',
          onDisconnect: () => _run(widget.client.disconnectFitbit, 'Couldn\'t disconnect Fitbit'),
          connectControl: SkyButton(
            label: 'Connect',
            kind: SkyButtonKind.primary,
            onPressed: _busy ? null : _connectFitbit,
          ),
        ),
      ]),
      if (!_fitbit.connected && !_fitbit.loading && _fitbit.error == null)
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 10, 8, 0),
          child: Text('Fitbit opens in your browser; LifePete notices when you\'re done.',
              style: SkyType.body(13).copyWith(color: p.inkOnSky)),
        ),
    ]);
  }
}

/// Waits for the Fitbit sign-in finished in the browser: checks every four
/// seconds for up to three minutes and closes itself once Fitbit reports
/// connected.
class _FitbitWaitDialog extends StatefulWidget {
  final ApiClient client;
  const _FitbitWaitDialog({required this.client});

  @override
  State<_FitbitWaitDialog> createState() => _FitbitWaitDialogState();
}

class _FitbitWaitDialogState extends State<_FitbitWaitDialog> {
  static const _every = Duration(seconds: 4);
  static const _timeout = Duration(minutes: 3);
  Timer? _poll;
  Timer? _deadline;
  bool _connected = false;
  bool _gaveUp = false;

  @override
  void initState() {
    super.initState();
    unawaited(_check());
    _poll = Timer.periodic(_every, (_) => _check());
    _deadline = Timer(_timeout, () {
      if (!mounted) return;
      _poll?.cancel();
      setState(() => _gaveUp = true);
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _deadline?.cancel();
    super.dispose();
  }

  Future<void> _check() async {
    try {
      final s = await widget.client.getFitbitStatus();
      if (s['connected'] != true) return;
    } catch (_) {
      return; // A blip; the next tick tries again.
    }
    if (!mounted || _connected) return;
    _poll?.cancel();
    _deadline?.cancel();
    setState(() => _connected = true);
    await Future.delayed(const Duration(milliseconds: 700));
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final (color, title, body) = _connected
        ? (p.leaf, 'Fitbit connected', 'You\'re all set.')
        : _gaveUp
            ? (p.persimmon, 'Still waiting?',
                'Nothing back from Fitbit yet. If you authorised it, check now; otherwise close this and try Connect again.')
            : (p.sun, 'Finish in your browser',
                'A Fitbit page just opened. Once you choose Allow there, this closes on its own.');
    return AlertDialog(
      title: Row(children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 12),
        Expanded(child: Text(title, style: SkyType.display(20))),
      ]),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 380),
        child: Text(body, style: SkyType.body(14, height: 1.6).copyWith(color: p.inkMuted)),
      ),
      actions: [
        SkyButton(label: _connected ? 'Done' : 'Close', onPressed: () => Navigator.of(context).pop()),
        if (!_connected) SkyButton(label: 'Check now', kind: SkyButtonKind.primary, onPressed: _check),
      ],
    );
  }
}

// ─── Account ────────────────────────────────────────────────────────

class _AccountTab extends StatefulWidget {
  final ApiClient client;
  final VoidCallback onUnpaired;
  const _AccountTab({required this.client, required this.onUnpaired});

  @override
  State<_AccountTab> createState() => _AccountTabState();
}

class _AccountTabState extends State<_AccountTab> {
  final _storage = TokenStorage();
  bool _checking = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _heartbeat();
  }

  Future<void> _heartbeat() async {
    String? error;
    try {
      await widget.client.postHeartbeat();
    } catch (e) {
      error = shortError(e);
    }
    if (!mounted) return;
    setState(() {
      _checking = false;
      _error = error;
    });
  }

  Future<void> _openWeb() async {
    final base = await _storage.loadWebUrl();
    final trimmed = base.endsWith('/') ? base.substring(0, base.length - 1) : base;
    await launchUrl(Uri.parse('$trimmed/settings'), mode: LaunchMode.externalApplication);
  }

  Future<void> _unpair() async {
    final p = context.sky;
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(Platform.isMacOS ? 'Unpair this Mac?' : 'Unpair this device?', style: SkyType.display(20)),
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Text(
            'Your tracked time stays on the server. You\'ll need a new pairing code to use LifePete here again.',
            style: SkyType.body(14, height: 1.6).copyWith(color: p.inkMuted),
          ),
        ),
        actions: [
          SkyButton(label: 'Cancel', onPressed: () => Navigator.pop(ctx, false)),
          SkyButton(label: 'Unpair', kind: SkyButtonKind.danger, onPressed: () => Navigator.pop(ctx, true)),
        ],
      ),
    );
    if (yes != true) return;
    await _storage.deleteToken();
    widget.onUnpaired();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final host = Uri.tryParse(widget.client.baseUrl)?.host;
    final mac = Platform.isMacOS;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _Group([
        _Row(
          title: host == null || host.isEmpty ? widget.client.baseUrl : host,
          subtitle: _checking
              ? 'Checking…'
              : _error == null
                  ? 'Connected · checked just now'
                  : 'Can\'t reach it: $_error',
          leading: ProjectDot(
            color: _checking ? p.inkMuted : (_error == null ? p.leaf : p.persimmon),
          ),
          trailing: LinkButton(label: 'Account on the web', bold: true, color: p.sunInk, onPressed: _openWeb),
        ),
        _Row(
          title: 'This device',
          subtitle: mac ? 'Paired with this Mac' : 'Paired with this device',
          leading: Icon(mac ? Icons.laptop_mac_rounded : Icons.devices_rounded, size: 18, color: p.inkMuted),
        ),
      ]),
      const SizedBox(height: 18),
      Container(
        padding: const EdgeInsets.fromLTRB(20, 16, 16, 16),
        decoration: BoxDecoration(
          color: p.panel,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: p.persimmon.withValues(alpha: 0.45), width: 1.5),
        ),
        child: Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 16,
          runSpacing: 12,
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(mac ? 'Unpair this Mac' : 'Unpair this device',
                    style: SkyType.body(15, weight: FontWeight.w700).copyWith(color: p.persimmonInk)),
                const SizedBox(height: 4),
                Text(
                  'Your tracked time stays on the server. To use LifePete here again you\'ll need a new pairing code.',
                  style: SkyType.body(13).copyWith(color: p.inkMuted),
                ),
              ]),
            ),
            SkyButton(label: 'Unpair…', kind: SkyButtonKind.danger, onPressed: _unpair),
          ],
        ),
      ),
    ]);
  }
}
