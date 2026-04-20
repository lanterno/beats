import 'dart:io';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/token_storage.dart';
import '../theme/beats_theme.dart';

class PairingScreen extends StatefulWidget {
  final VoidCallback onPaired;
  const PairingScreen({super.key, required this.onPaired});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _codeController = TextEditingController();
  final _apiUrlController = TextEditingController();
  final _storage = TokenStorage();
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadApiUrl();
  }

  Future<void> _loadApiUrl() async {
    final url = await _storage.loadApiUrl();
    _apiUrlController.text = url;
  }

  Future<void> _pair() async {
    final code = _codeController.text.trim().toUpperCase();
    if (code.length != 6) {
      setState(() => _error = 'Enter a 6-character pairing code');
      return;
    }

    final apiUrl = _apiUrlController.text.trim();
    if (apiUrl.isEmpty) {
      setState(() => _error = 'Enter the API URL');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final client = ApiClient(baseUrl: apiUrl);
      final hostname = Platform.localHostname;
      final result = await client.exchangePairCode(code, deviceName: hostname);

      await _storage.saveToken(result.deviceToken);
      await _storage.saveApiUrl(apiUrl);

      if (mounted) {
        widget.onPaired();
      }
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 404
          ? 'Invalid or expired pairing code'
          : 'Pairing failed: ${e.message}');
    } catch (e) {
      setState(() => _error = 'Connection failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _codeController.dispose();
    _apiUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.link, size: 48, color: theme.colorScheme.primary),
                const SizedBox(height: 16),
                Text(
                  'Pair with Beats',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Open Beats Settings \u2192 Daemon \u2192 "Pair new device" to get a 6-character code.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                TextField(
                  controller: _apiUrlController,
                  decoration: const InputDecoration(
                    labelText: 'API URL',
                    hintText: 'http://localhost:7999',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _codeController,
                  decoration: const InputDecoration(
                    labelText: 'Pairing code',
                    hintText: 'ABC123',
                    border: OutlineInputBorder(),
                  ),
                  textCapitalization: TextCapitalization.characters,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineMedium?.copyWith(
                    letterSpacing: 8,
                    fontWeight: FontWeight.bold,
                  ),
                  maxLength: 6,
                  onSubmitted: (_) => _pair(),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.error, fontSize: 13),
                    textAlign: TextAlign.center,
                  ),
                ],
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _loading ? null : _pair,
                  child: _loading
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Pair'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
