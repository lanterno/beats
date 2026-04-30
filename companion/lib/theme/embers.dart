import 'dart:math' as math;
import 'package:flutter/material.dart';

import 'beats_theme.dart';

/// Slowly drifting ember dots — used as ambient backing for screens that
/// otherwise feel too still (notably the pairing screen, which has long
/// stretches of inactivity while the user pulls a code from the web UI).
///
/// Each ember is born at the bottom edge with a randomized lifetime,
/// horizontal drift, and base alpha; rises through the canvas; and respawns
/// from the bottom when its lifetime expires. The whole effect is driven by
/// a single AnimationController repeating every 30s — particles use modular
/// arithmetic against the controller's value so each one has its own phase.
class Embers extends StatefulWidget {
  final int count;
  final Color color;
  const Embers({super.key, this.count = 14, this.color = BeatsColors.amber});

  @override
  State<Embers> createState() => _EmbersState();
}

class _EmbersState extends State<Embers> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final List<_EmberSeed> _seeds;

  @override
  void initState() {
    super.initState();
    final rng = math.Random();
    _seeds = List.generate(widget.count, (_) => _EmberSeed.random(rng));
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 30),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (_, _) => CustomPaint(
          painter: _EmbersPainter(
            t: _controller.value,
            seeds: _seeds,
            color: widget.color,
          ),
          size: Size.infinite,
        ),
      ),
    );
  }
}

/// Random parameters for a single ember; stable for the lifetime of the
/// widget so motion is deterministic per-instance.
class _EmberSeed {
  final double xRatio; // 0..1, base horizontal position
  final double drift; // -0.05..0.05, lateral wobble amplitude
  final double phase; // 0..1, when in the cycle this ember starts
  final double speed; // 0.5..1.5, lifetime multiplier
  final double size; // 0.8..2.4 px
  final double maxAlpha; // 0.05..0.18

  const _EmberSeed({
    required this.xRatio,
    required this.drift,
    required this.phase,
    required this.speed,
    required this.size,
    required this.maxAlpha,
  });

  factory _EmberSeed.random(math.Random rng) => _EmberSeed(
        xRatio: rng.nextDouble(),
        drift: (rng.nextDouble() - 0.5) * 0.1,
        phase: rng.nextDouble(),
        speed: 0.5 + rng.nextDouble(),
        size: 0.8 + rng.nextDouble() * 1.6,
        maxAlpha: 0.05 + rng.nextDouble() * 0.13,
      );
}

class _EmbersPainter extends CustomPainter {
  final double t;
  final List<_EmberSeed> seeds;
  final Color color;
  const _EmbersPainter({
    required this.t,
    required this.seeds,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width == 0 || size.height == 0) return;
    for (final s in seeds) {
      // Each ember has its own phase, so lifetimes are staggered.
      final local = ((t * s.speed + s.phase) % 1.0).toDouble();

      // Slight horizontal wobble — sin wave over the lifetime.
      final wobble = math.sin(local * math.pi * 2) * s.drift;
      final x = ((s.xRatio + wobble) % 1.0) * size.width;

      // Rise from below the canvas to above it.
      final y = size.height * (1.05 - local * 1.1);

      // Fade in as it leaves the bottom, fade out before the top.
      // Triangle envelope peaking at local = 0.5.
      final envelope = 1 - (local * 2 - 1).abs();
      final alpha = (s.maxAlpha * envelope).clamp(0.0, 1.0);
      if (alpha <= 0) continue;

      canvas.drawCircle(
        Offset(x, y),
        s.size,
        Paint()
          ..color = color.withValues(alpha: alpha)
          ..isAntiAlias = true,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _EmbersPainter old) => old.t != t;
}
