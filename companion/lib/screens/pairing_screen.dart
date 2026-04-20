import 'dart:io';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../services/token_storage.dart';
import '../theme/beats_theme.dart';
import '../theme/staggered_entrance.dart';

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
      setState(() => _error = 'Enter a 6-character code');
      return;
    }
    final apiUrl = _apiUrlController.text.trim();
    if (apiUrl.isEmpty) {
      setState(() => _error = 'Enter the API URL');
      return;
    }
    setState(() { _loading = true; _error = null; });
    try {
      final client = ApiClient(baseUrl: apiUrl);
      final hostname = Platform.localHostname;
      final result = await client.exchangePairCode(code, deviceName: hostname);
      await _storage.saveToken(result.deviceToken);
      await _storage.saveApiUrl(apiUrl);
      if (mounted) widget.onPaired();
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 404
          ? 'Invalid or expired code' : 'Pairing failed: ${e.message}');
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
    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Logo mark
                StaggeredEntrance(
                  child: Center(
                    child: Container(
                      width: 56, height: 56,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: BeatsColors.amber.withValues(alpha: 0.1),
                        border: Border.all(color: BeatsColors.amber.withValues(alpha: 0.2)),
                      ),
                      child: Center(
                        child: Text('B',
                          style: GoogleFonts.dmSerifDisplay(
                            fontSize: 28, color: BeatsColors.amber)),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 24),

                StaggeredEntrance(
                  delay: const Duration(milliseconds: 60),
                  child: Center(
                    child: Text('Beats',
                      style: GoogleFonts.dmSerifDisplay(
                        fontSize: 28, color: BeatsColors.textPrimary)),
                  ),
                ),
                const SizedBox(height: 8),
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 100),
                  child: Center(
                    child: Text(
                      'Open Settings → Daemon → Pair to get a code',
                      style: BeatsType.bodySmall.copyWith(color: BeatsColors.textTertiary),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
                const SizedBox(height: 40),

                // API URL
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 140),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('API', style: BeatsType.label),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _apiUrlController,
                        style: BeatsType.bodyMedium,
                        decoration: _inputDecoration('https://api.lifepete.com'),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),

                // Code
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 180),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('CODE', style: BeatsType.label),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _codeController,
                        textCapitalization: TextCapitalization.characters,
                        textAlign: TextAlign.center,
                        maxLength: 6,
                        style: GoogleFonts.jetBrainsMono(
                          fontSize: 28, fontWeight: FontWeight.w400,
                          color: BeatsColors.textPrimary, letterSpacing: 12,
                        ),
                        decoration: _inputDecoration('ABC123').copyWith(
                          counterText: '',
                        ),
                        onSubmitted: (_) => _pair(),
                      ),
                    ],
                  ),
                ),

                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!,
                    style: BeatsType.bodySmall.copyWith(color: BeatsColors.red),
                    textAlign: TextAlign.center),
                ],
                const SizedBox(height: 24),

                // Pair button
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 220),
                  child: GestureDetector(
                    onTap: _loading ? null : _pair,
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      decoration: BoxDecoration(
                        color: BeatsColors.amber,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Center(
                        child: _loading
                            ? const SizedBox(width: 20, height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Color(0xFF1A1408)))
                            : Text('Pair', style: BeatsType.button.copyWith(
                                fontSize: 16, color: const Color(0xFF1A1408))),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  InputDecoration _inputDecoration(String hint) => InputDecoration(
    hintText: hint,
    hintStyle: BeatsType.bodyMedium.copyWith(color: BeatsColors.textTertiary.withValues(alpha: 0.4)),
    filled: true,
    fillColor: BeatsColors.surface,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide(color: BeatsColors.border)),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide(color: BeatsColors.border)),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide(color: BeatsColors.amber.withValues(alpha: 0.4))),
    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
  );
}
