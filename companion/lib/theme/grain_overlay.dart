import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Subtle grain/noise texture rendered as sparse, semi-transparent dots.
///
/// The pattern is deterministic per [seed], so the grain doesn't shimmer when
/// the parent rebuilds. Wrapped in a [RepaintBoundary] so a parent that
/// repaints frequently (e.g. an animated stat strip) doesn't redraw the
/// noise on every frame.
///
/// Designed for a "warm, hand-crafted" surface treatment — keep [opacity]
/// low (≤ 0.07). Higher values turn it from texture into snow.
class GrainOverlay extends StatelessWidget {
  /// Roughly the number of dots per 10 000 pixels² of the painted area.
  /// Defaults to a density that reads as texture rather than as stippling.
  final double density;
  final double opacity;
  final int seed;
  final Color tint;

  const GrainOverlay({
    super.key,
    this.density = 1.4,
    this.opacity = 0.05,
    this.seed = 42,
    this.tint = const Color(0xFFF0E8DC),
  });

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: IgnorePointer(
        child: CustomPaint(
          painter: _GrainPainter(
            density: density,
            opacity: opacity,
            seed: seed,
            tint: tint,
          ),
          size: Size.infinite,
        ),
      ),
    );
  }
}

class _GrainPainter extends CustomPainter {
  final double density;
  final double opacity;
  final int seed;
  final Color tint;

  _GrainPainter({
    required this.density,
    required this.opacity,
    required this.seed,
    required this.tint,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;

    // density is per 10 000 px² so scale linearly with area.
    final count = (size.width * size.height / 10000 * density).round().clamp(0, 4000);
    final rng = math.Random(seed);
    final paint = Paint()..color = tint.withValues(alpha: opacity);

    for (var i = 0; i < count; i++) {
      final dx = rng.nextDouble() * size.width;
      final dy = rng.nextDouble() * size.height;
      // Mix dots and 1×1 rect "specks" so the grain doesn't look uniformly round.
      if (i.isEven) {
        canvas.drawCircle(Offset(dx, dy), 0.6, paint);
      } else {
        canvas.drawRect(Rect.fromLTWH(dx, dy, 1, 1), paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _GrainPainter old) =>
      old.density != density ||
      old.opacity != opacity ||
      old.seed != seed ||
      old.tint != tint;
}
