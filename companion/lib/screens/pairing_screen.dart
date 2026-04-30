import 'dart:io';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_client.dart';
import '../services/token_storage.dart';
import '../theme/beats_theme.dart';
import '../theme/embers.dart';
import '../theme/staggered_entrance.dart';

class PairingScreen extends StatefulWidget {
  final VoidCallback onPaired;
  const PairingScreen({super.key, required this.onPaired});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _codeController = TextEditingController();
  final _codeFocus = FocusNode();
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
    _codeFocus.dispose();
    _apiUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: BeatsColors.background,
      body: Stack(
        children: [
          // Ambient ember field behind the form — slow drift, very low alpha
          // so it never competes with the input fields for attention.
          const Positioned.fill(child: Embers()),
          Center(
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
                      _CodeInput(
                        controller: _codeController,
                        focusNode: _codeFocus,
                        onSubmitted: _pair,
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
        ],
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

/// 6-character code input rendered as individual boxes.
///
/// Backed by a single TextField (so paste, autofill, and keyboard navigation
/// all keep working) with its visible text/cursor stripped to transparent.
/// Six boxes float on top, reading off the controller — the active box (the
/// next empty slot) highlights amber.
class _CodeInput extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final VoidCallback onSubmitted;
  const _CodeInput({
    required this.controller,
    required this.focusNode,
    required this.onSubmitted,
  });

  @override
  State<_CodeInput> createState() => _CodeInputState();
}

class _CodeInputState extends State<_CodeInput> {
  static const _length = 6;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChanged);
    widget.focusNode.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    widget.focusNode.removeListener(_onFocusChanged);
    super.dispose();
  }

  void _onChanged() {
    final raw = widget.controller.text;
    final upper = raw.toUpperCase();
    if (upper != raw) {
      // Force-uppercase without losing the user's place in the field.
      widget.controller.value = TextEditingValue(
        text: upper,
        selection: TextSelection.collapsed(offset: upper.length),
      );
    }
    setState(() {});
  }

  void _onFocusChanged() => setState(() {});

  Widget _box({required String char, required bool isActive}) {
    final isFilled = char.isNotEmpty;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
      height: 56,
      decoration: BoxDecoration(
        color: BeatsColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isActive
              ? BeatsColors.amber
              : isFilled
                  ? BeatsColors.amber.withValues(alpha: 0.4)
                  : BeatsColors.border,
          width: isActive ? 1.6 : 1,
        ),
      ),
      alignment: Alignment.center,
      child: Text(
        char,
        style: GoogleFonts.jetBrainsMono(
          fontSize: 24,
          fontWeight: FontWeight.w400,
          color: BeatsColors.textPrimary,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final text = widget.controller.text;
    final focused = widget.focusNode.hasFocus;
    final activeIndex = text.length.clamp(0, _length - 1);

    return GestureDetector(
      onTap: () => widget.focusNode.requestFocus(),
      child: Stack(
        children: [
          // Visible boxes — non-interactive, painted underneath.
          IgnorePointer(
            child: Row(
              children: [
                for (var i = 0; i < _length; i++) ...[
                  if (i > 0) const SizedBox(width: 8),
                  Expanded(child: _box(
                    char: i < text.length ? text[i] : '',
                    isActive: focused && i == activeIndex,
                  )),
                ],
              ],
            ),
          ),
          // Invisible TextField sits on top to capture keystrokes / paste.
          // Sized to fill the box row.
          Positioned.fill(
            child: TextField(
              controller: widget.controller,
              focusNode: widget.focusNode,
              autofocus: false,
              textCapitalization: TextCapitalization.characters,
              textAlign: TextAlign.center,
              maxLength: _length,
              showCursor: false,
              keyboardType: TextInputType.text,
              onSubmitted: (_) => widget.onSubmitted(),
              style: const TextStyle(
                color: Colors.transparent,
                height: 1,
              ),
              decoration: const InputDecoration(
                counterText: '',
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                fillColor: Colors.transparent,
                filled: true,
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
