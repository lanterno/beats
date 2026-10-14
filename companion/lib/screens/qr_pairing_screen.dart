import 'dart:io';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../brand.dart';
import '../services/qr_pairing.dart';
import '../theme/sky.dart';

/// Camera-driven QR pairing for iOS / Android. Pops back with a
/// [QrPairingPayload] on the first successful scan. Returns null when
/// the user cancels or when invoked on an unsupported platform.
///
/// The `mobile_scanner` package only ships native bits for mobile; on
/// desktop / web the scanner widget will throw at runtime, so the
/// parent [PairingScreen] is responsible for only pushing this route
/// on `Platform.isIOS || Platform.isAndroid`.
class QrPairingScreen extends StatefulWidget {
  const QrPairingScreen({super.key});

  @override
  State<QrPairingScreen> createState() => _QrPairingScreenState();
}

class _QrPairingScreenState extends State<QrPairingScreen> {
  final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.normal,
    facing: CameraFacing.back,
  );
  bool _handled = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_handled) return;
    for (final barcode in capture.barcodes) {
      final parsed = parseQrPairingPayload(barcode.rawValue);
      if (parsed == null) continue;
      _handled = true;
      Navigator.of(context).pop(parsed);
      return;
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    if (!(Platform.isIOS || Platform.isAndroid)) {
      // Defensive: a desktop tap-through that bypasses the parent's gate
      // shouldn't crash the camera plugin.
      return Scaffold(
        backgroundColor: p.panel.withValues(alpha: 1),
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          foregroundColor: p.ink,
          title: Text('Scan QR', style: SkyType.display(20)),
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Text(
              'QR scanning is only available on iOS and Android. '
              'On desktop, type the 6-character code from your $appName web Settings.',
              textAlign: TextAlign.center,
              style: SkyType.body(15).copyWith(color: p.inkMuted),
            ),
          ),
        ),
      );
    }

    // The camera fills the screen, so the frame around it is ink in
    // either hour.
    return Scaffold(
      backgroundColor: SkyPalette.afternoon.ink,
      appBar: AppBar(
        backgroundColor: SkyPalette.afternoon.ink,
        foregroundColor: Colors.white,
        elevation: 0,
        title: Text('Scan QR', style: SkyType.display(20)),
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(
            controller: _controller,
            onDetect: _onDetect,
          ),
          // Subtle scan window — a square in the middle so the user knows
          // where to aim. Doesn't actually constrain detection (the
          // package scans the whole frame), it's just a visual guide.
          IgnorePointer(
            child: Center(
              child: Container(
                width: 240,
                height: 240,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: p.sun, width: 2),
                ),
              ),
            ),
          ),
          Positioned(
            left: 24, right: 24, bottom: 32,
            child: Text(
              'Point at the QR code shown in your $appName web Settings → Daemon',
              textAlign: TextAlign.center,
              style: SkyType.body(13).copyWith(color: Colors.white.withValues(alpha: 0.85)),
            ),
          ),
        ],
      ),
    );
  }
}
