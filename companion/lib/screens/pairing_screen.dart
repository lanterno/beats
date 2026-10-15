import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../brand.dart';
import '../services/api_client.dart';
import '../services/qr_pairing.dart';
import '../services/token_storage.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'qr_pairing_screen.dart';
import 'shell.dart' show BrandMark;

/// First run: pair this device with a LifePete account by typing the
/// six-character code the web app shows under Settings → Daemon.
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
  final _webUrlController = TextEditingController();
  final _storage = TokenStorage();
  bool _loading = false;
  bool _ownServer = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadUrls();
    _codeController.addListener(() => setState(() {}));
    _apiUrlController.addListener(() => setState(() {}));
    _webUrlController.addListener(() => setState(() {}));
  }

  Future<void> _loadUrls() async {
    // Hydrate both fields in one trip so the user sees their saved
    // values (or the defaults). Web URL was added later — existing
    // users who never set it land on http://localhost:8080.
    final api = await _storage.loadApiUrl();
    final web = await _storage.loadWebUrl();
    _apiUrlController.text = api;
    _webUrlController.text = web;
  }

  /// True on the platforms where `mobile_scanner` actually works
  /// (iOS / Android). Desktops show the code-entry path only.
  bool get _qrSupported => Platform.isIOS || Platform.isAndroid;

  /// Push the QR scanner; on success, autofill the code (and the API
  /// URL when the QR carried one) and immediately attempt to pair.
  Future<void> _scanQr() async {
    final result = await Navigator.of(context).push<QrPairingPayload?>(
      MaterialPageRoute(builder: (_) => const QrPairingScreen()),
    );
    if (result == null || !mounted) return;
    setState(() {
      _codeController.text = result.code;
      if (result.apiUrl != null) {
        _apiUrlController.text = result.apiUrl!;
      }
      _error = null;
    });
    await _pair();
  }

  Future<void> _pair() async {
    final code = _codeController.text.trim().toUpperCase();
    if (code.length != 6) {
      setState(() => _error = 'Enter a 6-character code');
      return;
    }
    final apiUrl = _apiUrlController.text.trim();
    if (apiUrl.isEmpty) {
      setState(() {
        _ownServer = true;
        _error = 'Enter the API URL';
      });
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
      // Web URL is optional — if blank, leave the saved/default value alone
      // so a user who only filled in the API field doesn't clobber it.
      final webUrl = _webUrlController.text.trim();
      if (webUrl.isNotEmpty) {
        await _storage.saveWebUrl(webUrl);
      }
      if (mounted) widget.onPaired();
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 404 ? 'Invalid or expired code' : 'Pairing failed: ${e.message}');
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
    _webUrlController.dispose();
    super.dispose();
  }

  String _host(String url, String fallback) {
    final host = Uri.tryParse(url.trim())?.host ?? '';
    return host.isEmpty ? fallback : host;
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final isMac = Platform.isMacOS;
    final webHost = _host(_webUrlController.text, 'the web app');
    final apiHost = _host(_apiUrlController.text, 'your server');

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SkyBackdrop(
        hills: true,
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 48),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 500),
              child: Panel(
                raised: true,
                radius: 30,
                padding: isCompact(context)
                    ? const EdgeInsets.fromLTRB(22, 28, 22, 22)
                    : const EdgeInsets.fromLTRB(38, 34, 38, 28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: BrandMark(size: 60)),
                    const SizedBox(height: 14),
                    Semantics(
                      header: true,
                      child: Text(
                        isMac ? 'Pair this Mac' : 'Pair this device',
                        textAlign: TextAlign.center,
                        style: SkyType.display(26),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      isMac
                          ? 'Once paired, $appName lives in your menu bar and keeps your timer one click away.'
                          : 'Once paired, $appName keeps your timer one tap away.',
                      textAlign: TextAlign.center,
                      style: SkyType.body(15, height: 1.6).copyWith(color: p.inkOnSky),
                    ),
                    const SizedBox(height: 22),
                    _Step(n: 1, text: 'Open $webHost → Settings → Daemon'),
                    const SizedBox(height: 10),
                    // A phone scans the code; typing it is the fallback.
                    _Step(
                      n: 2,
                      text: _qrSupported
                          ? 'Choose Pair, then scan the code it shows'
                          : 'Choose Pair and type the six characters here',
                    ),
                    const SizedBox(height: 22),
                    if (_qrSupported) ...[
                      SizedBox(
                        height: 52,
                        child: SkyButton(
                          label: 'Scan the code',
                          icon: Icons.qr_code_scanner_rounded,
                          kind: SkyButtonKind.primary,
                          large: true,
                          onPressed: _loading ? null : _scanQr,
                        ),
                      ),
                      const SizedBox(height: 22),
                    ],
                    Text(_qrSupported ? 'Or type the six characters' : 'Pairing code',
                        style: SkyType.body(13, weight: FontWeight.w700).copyWith(color: p.inkOnSky)),
                    const SizedBox(height: 8),
                    _CodeBoxes(
                      controller: _codeController,
                      focusNode: _codeFocus,
                      onSubmit: _pair,
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 10),
                      Text(_error!, style: SkyType.body(13).copyWith(color: p.persimmonInk)),
                    ],
                    const SizedBox(height: 20),
                    SizedBox(
                      height: 50,
                      child: SkyButton(
                        label: 'Pair',
                        kind: _qrSupported ? SkyButtonKind.secondary : SkyButtonKind.primary,
                        large: true,
                        leading: _loading
                            ? SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: p.onSun),
                              )
                            : null,
                        onPressed: _loading ? null : _pair,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Wrap(
                      alignment: WrapAlignment.center,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: 6,
                      children: [
                        ProjectDot(color: p.leaf, size: 8),
                        Text('Pairing with $apiHost', style: SkyType.body(13).copyWith(color: p.inkOnSky)),
                        if (!_ownServer)
                          LinkButton(
                            label: 'Use my own server',
                            bold: true,
                            color: p.sunInk,
                            onPressed: () => setState(() => _ownServer = true),
                          ),
                      ],
                    ),
                    if (_ownServer) ...[
                      const SizedBox(height: 12),
                      _UrlField(label: 'API URL', controller: _apiUrlController, hint: 'https://api.example.com'),
                      const SizedBox(height: 10),
                      _UrlField(
                        label: 'Web app URL (optional)',
                        controller: _webUrlController,
                        hint: 'https://example.com',
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Step extends StatelessWidget {
  final int n;
  final String text;
  const _Step({required this.n, required this.text});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        width: 26,
        height: 26,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: p.wash, shape: BoxShape.circle),
        child: Text('$n', style: SkyType.figure(13, weight: FontWeight.w700)),
      ),
      const SizedBox(width: 12),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.only(top: 3),
          child: Text(text, style: SkyType.body(15)),
        ),
      ),
    ]);
  }
}

/// Six boxes showing the code, driven by one text field laid over them so
/// typing, deleting and pasting a whole code all behave like one input.
class _CodeBoxes extends StatelessWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final VoidCallback onSubmit;

  const _CodeBoxes({required this.controller, required this.focusNode, required this.onSubmit});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final code = controller.text;
    return ListenableBuilder(
      listenable: focusNode,
      builder: (context, _) => Stack(children: [
        Row(children: [
          for (var i = 0; i < 6; i++) ...[
            if (i > 0) const SizedBox(width: 8),
            Expanded(
              child: Container(
                height: 58,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: focusNode.hasFocus && i == code.length.clamp(0, 5) ? p.panel.withValues(alpha: 1) : p.wash,
                  borderRadius: BorderRadius.circular(16),
                  border: focusNode.hasFocus && i == code.length.clamp(0, 5)
                      ? Border.all(color: p.sun, width: 2)
                      : null,
                ),
                child: Text(i < code.length ? code[i] : '', style: SkyType.figure(26)),
              ),
            ),
          ],
        ]),
        Positioned.fill(
          child: Semantics(
            label: 'Pairing code',
            child: TextField(
              key: const Key('pairing-code'),
              controller: controller,
              focusNode: focusNode,
              autofocus: true,
              maxLength: 6,
              textCapitalization: TextCapitalization.characters,
              textInputAction: TextInputAction.go,
              onSubmitted: (_) => onSubmit(),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z0-9]')),
                TextInputFormatter.withFunction(
                  (_, v) => v.copyWith(text: v.text.toUpperCase()),
                ),
                LengthLimitingTextInputFormatter(6),
              ],
              showCursor: false,
              enableInteractiveSelection: true,
              style: const TextStyle(color: Colors.transparent, fontSize: 1),
              cursorColor: Colors.transparent,
              decoration: const InputDecoration(
                counterText: '',
                filled: false,
                border: InputBorder.none,
                focusedBorder: InputBorder.none,
                enabledBorder: InputBorder.none,
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

class _UrlField extends StatelessWidget {
  final String label;
  final String hint;
  final TextEditingController controller;
  const _UrlField({required this.label, required this.controller, required this.hint});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: SkyType.body(13, weight: FontWeight.w700).copyWith(color: p.inkOnSky)),
      const SizedBox(height: 6),
      TextField(
        controller: controller,
        keyboardType: TextInputType.url,
        autocorrect: false,
        style: SkyType.body(15),
        decoration: InputDecoration(hintText: hint),
      ),
    ]);
  }
}
