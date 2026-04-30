import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../services/token_storage.dart';
import '../theme/beats_refresh.dart';
import '../theme/beats_theme.dart';
import '../theme/press_scale.dart';
import '../theme/staggered_entrance.dart';

class HomeScreen extends StatefulWidget {
  final VoidCallback onUnpaired;
  const HomeScreen({super.key, required this.onUnpaired});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _storage = TokenStorage();
  final _ouraPatController = TextEditingController();
  ApiClient? _client;
  bool _heartbeatOk = false;
  bool _loading = true;
  String? _heartbeatError;

  // Integration status
  bool _fitbitConnected = false;
  String? _fitbitUser;
  bool _ouraConnected = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final token = await _storage.loadToken();
    final apiUrl = await _storage.loadApiUrl();
    if (token == null) {
      widget.onUnpaired();
      return;
    }

    _client = ApiClient(baseUrl: apiUrl, deviceToken: token);
    await _sendHeartbeat();
    await _refreshIntegrations();
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _sendHeartbeat() async {
    try {
      await _client!.postHeartbeat();
      if (mounted) {
        setState(() {
          _heartbeatOk = true;
          _heartbeatError = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _heartbeatOk = false;
          _heartbeatError = e.toString();
        });
      }
    }
  }

  Future<void> _refreshIntegrations() async {
    try {
      final fitbit = await _client!.getFitbitStatus();
      final oura = await _client!.getOuraStatus();
      if (mounted) {
        setState(() {
          _fitbitConnected = fitbit['connected'] == true;
          _fitbitUser = fitbit['fitbit_user_id'];
          _ouraConnected = oura['connected'] == true;
        });
      }
    } catch (_) {
      // Integrations status is non-critical
    }
  }

  Future<void> _refreshAll() async {
    setState(() => _loading = true);
    await _sendHeartbeat();
    await _refreshIntegrations();
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _confirmUnpair() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: BeatsColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Unpair this device?',
                style: GoogleFonts.dmSerifDisplay(
                  fontSize: 20, color: BeatsColors.textPrimary)),
              const SizedBox(height: 12),
              Text(
                'You\'ll need a fresh pairing code from Beats Settings to use this app again.',
                style: BeatsType.bodySmall.copyWith(
                  color: BeatsColors.textTertiary, height: 1.5),
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(child: PressScale(
                    onTap: () => Navigator.pop(ctx, false),
                    child: Container(
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: BeatsColors.border),
                      ),
                      child: Text('Cancel', style: BeatsType.button.copyWith(
                        color: BeatsColors.textTertiary)),
                    ),
                  )),
                  const SizedBox(width: 10),
                  Expanded(child: PressScale(
                    onTap: () => Navigator.pop(ctx, true),
                    child: Container(
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(
                        color: BeatsColors.red.withValues(alpha: 0.85),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text('Unpair', style: BeatsType.button.copyWith(
                        color: Colors.white)),
                    ),
                  )),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    if (confirmed != true) return;
    await _storage.deleteToken();
    if (mounted) widget.onUnpaired();
  }

  Future<void> _connectOura() async {
    final pat = _ouraPatController.text.trim();
    if (pat.isEmpty) return;
    try {
      await _client!.connectOura(pat);
      _ouraPatController.clear();
      await _refreshIntegrations();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Oura connected'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed: $e'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  Future<void> _disconnectOura() async {
    try {
      await _client!.disconnectOura();
      await _refreshIntegrations();
    } catch (_) {}
  }

  Future<void> _disconnectFitbit() async {
    try {
      await _client!.disconnectFitbit();
      await _refreshIntegrations();
    } catch (_) {}
  }

  @override
  void dispose() {
    _ouraPatController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: BeatsColors.background,
        body: Center(child: CircularProgressIndicator(color: BeatsColors.amber)),
      );
    }

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: SafeArea(
        child: BeatsRefresh(
          onRefresh: _refreshAll,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
            children: [
              // ── Header ──
              StaggeredEntrance(
                child: Row(
                  children: [
                    Text('Settings',
                      style: GoogleFonts.dmSerifDisplay(
                        fontSize: 32, color: BeatsColors.textPrimary)),
                    const Spacer(),
                    PressScale(
                      onTap: _refreshAll,
                      child: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: BeatsColors.surface,
                          border: Border.all(color: BeatsColors.border),
                        ),
                        child: Icon(Icons.refresh,
                          size: 18, color: BeatsColors.textTertiary),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),

              // ── Connection ──
              _SectionHeader(label: 'CONNECTION'),
              const SizedBox(height: 12),
              StaggeredEntrance(
                delay: const Duration(milliseconds: 60),
                child: _StatusRow(
                  ok: _heartbeatOk,
                  title: _heartbeatOk
                      ? 'Connected to Beats'
                      : 'Connection failed',
                  subtitle: _heartbeatOk
                      ? 'Heartbeat OK'
                      : (_heartbeatError ?? 'Unable to reach the API'),
                ),
              ),
              const SizedBox(height: 28),

              // ── Integrations ──
              _SectionHeader(label: 'INTEGRATIONS'),
              const SizedBox(height: 12),
              StaggeredEntrance(
                delay: const Duration(milliseconds: 100),
                child: _IntegrationRow(
                  name: 'Fitbit',
                  connected: _fitbitConnected,
                  detail: _fitbitConnected
                      ? (_fitbitUser ?? 'Connected')
                      : 'Connect via Beats web Settings',
                  trailing: _fitbitConnected
                      ? _LinkAction(label: 'Disconnect', onTap: _disconnectFitbit)
                      : null,
                ),
              ),
              const SizedBox(height: 8),
              StaggeredEntrance(
                delay: const Duration(milliseconds: 140),
                child: _OuraRow(
                  connected: _ouraConnected,
                  controller: _ouraPatController,
                  onConnect: _connectOura,
                  onDisconnect: _disconnectOura,
                ),
              ),
              const SizedBox(height: 40),

              // ── Danger zone ──
              _SectionHeader(label: 'DANGER ZONE', tint: BeatsColors.red),
              const SizedBox(height: 12),
              StaggeredEntrance(
                delay: const Duration(milliseconds: 180),
                child: PressScale(
                  onTap: _confirmUnpair,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 14),
                    decoration: BoxDecoration(
                      color: BeatsColors.red.withValues(alpha: 0.06),
                      border: Border.all(
                          color: BeatsColors.red.withValues(alpha: 0.3)),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.link_off, size: 16, color: BeatsColors.red),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Unpair this device',
                                style: BeatsType.bodyMedium.copyWith(
                                  color: BeatsColors.red,
                                  fontWeight: FontWeight.w500,
                                )),
                              const SizedBox(height: 2),
                              Text('Sign out and forget the API URL',
                                style: BeatsType.bodySmall.copyWith(
                                  fontSize: 11,
                                  color: BeatsColors.textTertiary,
                                )),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─── Building blocks ────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final String label;
  final Color? tint;
  const _SectionHeader({required this.label, this.tint});

  @override
  Widget build(BuildContext context) {
    final color = tint ?? BeatsColors.textTertiary;
    return Row(
      children: [
        Text(label,
          style: BeatsType.label.copyWith(
            letterSpacing: 2.5, color: color,
          )),
        const SizedBox(width: 12),
        Expanded(
          child: Container(
            height: 1,
            color: color.withValues(alpha: 0.12),
          ),
        ),
      ],
    );
  }
}

class _StatusRow extends StatelessWidget {
  final bool ok;
  final String title;
  final String subtitle;
  const _StatusRow({required this.ok, required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    final dotColor = ok ? BeatsColors.green : BeatsColors.red;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: BeatsColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 8, height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: dotColor,
              boxShadow: [
                BoxShadow(
                  color: dotColor.withValues(alpha: 0.4),
                  blurRadius: 6, spreadRadius: 1,
                ),
              ],
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: BeatsType.bodyMedium),
                const SizedBox(height: 2),
                Text(subtitle,
                  style: BeatsType.bodySmall.copyWith(
                    fontSize: 11, color: BeatsColors.textTertiary)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _IntegrationRow extends StatelessWidget {
  final String name;
  final bool connected;
  final String detail;
  final Widget? trailing;
  const _IntegrationRow({
    required this.name,
    required this.connected,
    required this.detail,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final dotColor = connected ? BeatsColors.green : BeatsColors.textTertiary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: BeatsColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 8, height: 8,
            decoration: BoxDecoration(shape: BoxShape.circle, color: dotColor)),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: BeatsType.bodyMedium),
                const SizedBox(height: 2),
                Text(detail,
                  style: BeatsType.bodySmall.copyWith(
                    fontSize: 11, color: BeatsColors.textTertiary)),
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

class _OuraRow extends StatelessWidget {
  final bool connected;
  final TextEditingController controller;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;
  const _OuraRow({
    required this.connected,
    required this.controller,
    required this.onConnect,
    required this.onDisconnect,
  });

  @override
  Widget build(BuildContext context) {
    final dotColor = connected ? BeatsColors.green : BeatsColors.textTertiary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: BeatsColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8, height: 8,
                decoration: BoxDecoration(shape: BoxShape.circle, color: dotColor)),
              const SizedBox(width: 14),
              Expanded(child: Text('Oura', style: BeatsType.bodyMedium)),
              if (connected)
                _LinkAction(label: 'Disconnect', onTap: onDisconnect),
            ],
          ),
          if (!connected) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: controller,
                    obscureText: true,
                    style: BeatsType.bodySmall,
                    cursorColor: BeatsColors.amber,
                    decoration: InputDecoration(
                      hintText: 'Personal access token',
                      hintStyle: BeatsType.bodySmall.copyWith(
                        color: BeatsColors.textTertiary.withValues(alpha: 0.5)),
                      isDense: true,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 10),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(color: BeatsColors.border)),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(
                            color: BeatsColors.amber.withValues(alpha: 0.6))),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                PressScale(
                  onTap: onConnect,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: BeatsColors.amber,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text('Connect', style: BeatsType.button.copyWith(
                      fontSize: 13, color: const Color(0xFF1A1408))),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _LinkAction extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _LinkAction({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return PressScale(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
        child: Text(label,
          style: BeatsType.label.copyWith(
            letterSpacing: 1.5,
            color: BeatsColors.textTertiary,
            decoration: TextDecoration.underline,
            decorationColor: BeatsColors.textTertiary.withValues(alpha: 0.4),
          )),
      ),
    );
  }
}
