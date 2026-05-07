import 'dart:io';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../services/qr_pairing.dart';
import '../theme/beats_theme.dart';

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
    if (!(Platform.isIOS || Platform.isAndroid)) {
      // Defensive: a desktop tap-through that bypasses the parent's gate
      // shouldn't crash the camera plugin.
      return Scaffold(
        backgroundColor: BeatsColors.background,
        appBar: AppBar(
          backgroundColor: BeatsColors.background,
          foregroundColor: BeatsColors.textPrimary,
          title: const Text('Scan QR'),
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Text(
              'QR scanning is only available on iOS and Android. '
              'On desktop, type the 6-character code from your Beats web Settings.',
              textAlign: TextAlign.center,
              style: BeatsType.bodyMedium.copyWith(color: BeatsColors.textSecondary),
            ),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: BeatsColors.background,
      appBar: AppBar(
        backgroundColor: BeatsColors.background,
        foregroundColor: BeatsColors.textPrimary,
        elevation: 0,
        title: Text('Scan QR', style: GoogleFonts.dmSerifDisplay(fontSize: 22)),
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
                  border: Border.all(color: BeatsColors.amber, width: 2),
                ),
              ),
            ),
          ),
          Positioned(
            left: 24, right: 24, bottom: 32,
            child: Text(
              'Point at the QR code shown in your Beats web Settings → Daemon',
              textAlign: TextAlign.center,
              style: BeatsType.bodySmall.copyWith(
                color: BeatsColors.textPrimary.withValues(alpha: 0.85),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
