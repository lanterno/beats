import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:path_provider/path_provider.dart';

/// Renders solid-color circular tray icons on demand and caches them on disk.
///
/// macOS / Windows / Linux all want a file path for the menu-bar icon, so we
/// rasterize a small PNG once per project color and reuse it on subsequent
/// updates. Caching is keyed by the canonicalized hex string, so repeated
/// switches between the same projects don't touch disk or the GPU again.
class TrayIconRenderer {
  static const _idleHex = '7A7A7A';

  // Render at 2x the ~18pt visual size so retina menu bars stay crisp.
  static const _renderSize = 36;

  final Map<String, String> _cache = {};
  Directory? _dir;

  /// Returns a path to a colored dot icon for the project. Falls back to a
  /// neutral gray dot for the idle state or invalid inputs.
  Future<String> iconForProject(List<int>? rgb) async {
    final hex = _hexFromRgb(rgb) ?? _idleHex;
    return iconForHex(hex);
  }

  Future<String> idleIcon() => iconForHex(_idleHex);

  /// Renders a tiny flow-score sparkline behind a colored dot, baked into
  /// a PNG that the tray plugins will load.
  ///
  /// The sparkline gives a glanceable read on the last ~90 min of flow:
  /// peaks read green, dips read red, and the dot in the bottom-right
  /// corner anchors the icon to the running project's color so the icon
  /// still tells you "you're in project X" at a glance.
  ///
  /// [scores] is an ordered list of values in [0, 1] — most recent last.
  /// Empty or all-null inputs fall back to a plain dot for the project.
  Future<String> iconForSparkline(List<double> scores, List<int>? rgb) async {
    final hex = _hexFromRgb(rgb) ?? _idleHex;
    if (scores.isEmpty) return iconForHex(hex);

    // One sparkline file per project hex — overwritten on every refresh.
    // The data shifts every poll anyway; a per-fingerprint cache would
    // fill the temp dir over a long session without saving meaningful
    // work (each render is sub-millisecond).
    final dir = await _ensureDir();
    final file = File('${dir.path}/tray_spark_$hex.png');
    final bytes = await _renderSparkline(scores, hex);
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }

  Future<String> iconForHex(String hex) async {
    final key = hex.toUpperCase();
    final cached = _cache[key];
    if (cached != null && File(cached).existsSync()) return cached;

    final dir = await _ensureDir();
    final file = File('${dir.path}/tray_$key.png');
    if (!file.existsSync()) {
      final bytes = await _renderDot(key);
      await file.writeAsBytes(bytes, flush: true);
    }
    _cache[key] = file.path;
    return file.path;
  }

  Future<Directory> _ensureDir() async {
    final existing = _dir;
    if (existing != null) return existing;
    final tmp = await getTemporaryDirectory();
    final dir = Directory('${tmp.path}/beats_tray_icons');
    if (!dir.existsSync()) dir.createSync(recursive: true);
    _dir = dir;
    return dir;
  }

  Future<Uint8List> _renderDot(String hex) async {
    final color = _parseHex(hex);
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);

    // Inset slightly so the dot doesn't kiss the menu bar edges.
    const radius = _renderSize / 2.0 - 3.0;
    final center = ui.Offset(_renderSize / 2.0, _renderSize / 2.0);
    final paint = ui.Paint()
      ..color = color
      ..isAntiAlias = true;
    canvas.drawCircle(center, radius, paint);

    final picture = recorder.endRecording();
    final image = await picture.toImage(_renderSize, _renderSize);
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
    picture.dispose();
    image.dispose();
    return byteData!.buffer.asUint8List();
  }

  Future<Uint8List> _renderSparkline(List<double> scores, String hex) async {
    final dotColor = _parseHex(hex);
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);

    // Sparkline lives in the top-left ~24×24 of the icon. The project dot
    // anchors in the bottom-right corner so the icon still reads as "your
    // project" at a glance, even when the line is busy.
    final clamped = scores.map((s) => s.clamp(0.0, 1.0).toDouble()).toList();
    final n = clamped.length;
    final stroke = ui.Paint()
      ..color = const ui.Color(0xFFD4952A)
      ..isAntiAlias = true
      ..style = ui.PaintingStyle.stroke
      ..strokeWidth = 2.0
      ..strokeCap = ui.StrokeCap.round
      ..strokeJoin = ui.StrokeJoin.round;

    final path = ui.Path();
    const left = 2.0;
    const top = 4.0;
    const right = 28.0;
    const bottom = 28.0;
    for (var i = 0; i < n; i++) {
      final x = left + (right - left) * (n == 1 ? 0.5 : i / (n - 1));
      final y = bottom - (bottom - top) * clamped[i];
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, stroke);

    // Project dot anchored bottom-right.
    final dotPaint = ui.Paint()
      ..color = dotColor
      ..isAntiAlias = true;
    canvas.drawCircle(const ui.Offset(28, 28), 6, dotPaint);

    final picture = recorder.endRecording();
    final image = await picture.toImage(_renderSize, _renderSize);
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
    picture.dispose();
    image.dispose();
    return byteData!.buffer.asUint8List();
  }

  // Static methods kept for backwards-compat with the existing call
  // sites; delegate to the pure top-level functions below so tests
  // can hit them without instantiating the renderer.
  static String? _hexFromRgb(List<int>? rgb) => trayHexFromRgb(rgb);

  static ui.Color _parseHex(String hex) => trayParseHex(hex);
}

/// Pure helpers for the tray-icon color path, lifted out of
/// [TrayIconRenderer] so they can be unit tested without spinning up
/// `path_provider` or rasterizing PNGs. The rendering pipeline still
/// lives in the renderer; these just normalize inputs.

/// Encodes a project's [r, g, b] tuple as a six-char uppercase hex
/// string (no `#`). Returns null when the list is missing or
/// malformed — the caller falls back to the idle gray. Each
/// component is clamped to 0..255 so a stray negative or 256+ value
/// from upstream JSON doesn't blow up `toRadixString`.
String? trayHexFromRgb(List<int>? rgb) {
  if (rgb == null || rgb.length < 3) return null;
  String hex(int v) => v.clamp(0, 255).toRadixString(16).padLeft(2, '0');
  return '${hex(rgb[0])}${hex(rgb[1])}${hex(rgb[2])}';
}

/// Parses a hex string (with or without `#`) into a fully-opaque
/// [ui.Color]. Falls back to the neutral gray on any parse error so
/// the tray always has SOMETHING to render — never a blank icon.
ui.Color trayParseHex(String hex) {
  final cleaned = hex.replaceFirst('#', '');
  final value = int.tryParse(cleaned, radix: 16) ?? 0x7A7A7A;
  return ui.Color(0xFF000000 | value);
}
