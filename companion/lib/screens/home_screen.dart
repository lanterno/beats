import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/token_storage.dart';

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
      if (mounted) setState(() => _heartbeatOk = true);
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

  Future<void> _unpair() async {
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
          const SnackBar(content: Text('Oura connected')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
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
    final theme = Theme.of(context);

    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Beats Companion'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () async {
              setState(() => _loading = true);
              await _sendHeartbeat();
              await _refreshIntegrations();
              setState(() => _loading = false);
            },
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          // Connection status
          _StatusCard(
            icon: _heartbeatOk ? Icons.check_circle : Icons.error,
            color: _heartbeatOk ? Colors.green : Colors.red,
            title: _heartbeatOk ? 'Connected to Beats' : 'Connection failed',
            subtitle: _heartbeatError ?? 'Heartbeat OK',
          ),
          const SizedBox(height: 24),

          // Integrations
          Text('Integrations',
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),

          // Fitbit
          _IntegrationTile(
            icon: Icons.favorite,
            name: 'Fitbit',
            connected: _fitbitConnected,
            detail: _fitbitUser,
            onDisconnect: _disconnectFitbit,
            onConnect: null, // OAuth needs browser — use web UI
            connectHint: 'Connect via Beats web Settings',
          ),
          const SizedBox(height: 8),

          // Oura
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.ring_volume, color: theme.colorScheme.primary, size: 20),
                      const SizedBox(width: 8),
                      Text('Oura', style: theme.textTheme.titleSmall),
                      const Spacer(),
                      if (_ouraConnected)
                        Chip(
                          label: const Text('Connected'),
                          backgroundColor: Colors.green.withValues(alpha: 0.1),
                          labelStyle: const TextStyle(color: Colors.green, fontSize: 12),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_ouraConnected)
                    TextButton(
                      onPressed: _disconnectOura,
                      child: const Text('Disconnect'),
                    )
                  else ...[
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _ouraPatController,
                            obscureText: true,
                            decoration: const InputDecoration(
                              hintText: 'Oura personal access token',
                              border: OutlineInputBorder(),
                              isDense: true,
                            ),
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                        const SizedBox(width: 8),
                        FilledButton(
                          onPressed: _connectOura,
                          child: const Text('Connect'),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 32),

          // Unpair
          OutlinedButton.icon(
            onPressed: _unpair,
            icon: const Icon(Icons.link_off),
            label: const Text('Unpair this device'),
            style: OutlinedButton.styleFrom(
              foregroundColor: theme.colorScheme.error,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;

  const _StatusCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Icon(icon, color: color, size: 32),
            const SizedBox(width: 16),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleSmall),
                Text(subtitle,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                    )),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _IntegrationTile extends StatelessWidget {
  final IconData icon;
  final String name;
  final bool connected;
  final String? detail;
  final VoidCallback? onConnect;
  final VoidCallback onDisconnect;
  final String? connectHint;

  const _IntegrationTile({
    required this.icon,
    required this.name,
    required this.connected,
    this.detail,
    this.onConnect,
    required this.onDisconnect,
    this.connectHint,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: ListTile(
        leading: Icon(icon, color: theme.colorScheme.primary),
        title: Text(name),
        subtitle: connected
            ? Text(detail ?? 'Connected')
            : Text(connectHint ?? 'Not connected'),
        trailing: connected
            ? TextButton(onPressed: onDisconnect, child: const Text('Disconnect'))
            : onConnect != null
                ? FilledButton(onPressed: onConnect, child: const Text('Connect'))
                : null,
      ),
    );
  }
}
