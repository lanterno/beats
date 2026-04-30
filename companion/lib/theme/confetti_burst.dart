import 'dart:math' as math;
import 'package:flutter/material.dart';

/// A tiny ephemeral particle burst used for completion micro-feedback (e.g.
/// checking off an intention). Renders a handful of small dots that fan
/// outward, fall slightly, and fade.
///
/// The widget is one-shot: it animates on first build and calls [onComplete]
/// when the animation finishes so the caller can remove it from the overlay.
class ConfettiBurst extends StatefulWidget {
  final Offset origin;
  final VoidCallback? onComplete;
  final List<Color> colors;
  final int count;
  final double radius;

  const ConfettiBurst({
    super.key,
    required this.origin,
    this.onComplete,
    this.colors = const [
      Color(0xFFD4952A), // amber
      Color(0xFFE9B85F), // amber light
      Color(0xFFF6CE7E), // gold pale
    ],
    this.count = 6,
    this.radius = 36,
  });

  @override
  State<ConfettiBurst> createState() => _ConfettiBurstState();
}

class _ConfettiBurstState extends State<ConfettiBurst>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final List<_Particle> _particles;

  @override
  void initState() {
    super.initState();
    final rng = math.Random();
    _particles = List.generate(widget.count, (i) {
      // Spread particles around the upper hemisphere with mild jitter so
      // bursts don't all fan in the same direction.
      final base = -math.pi / 2 + (i / widget.count - 0.5) * math.pi * 0.85;
      final angle = base + (rng.nextDouble() - 0.5) * 0.3;
      final speed = 0.7 + rng.nextDouble() * 0.5; // 0.7..1.2
      final size = 2.5 + rng.nextDouble() * 1.5;
      final color = widget.colors[rng.nextInt(widget.colors.length)];
      return _Particle(angle: angle, speed: speed, size: size, color: color);
    });
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 650),
    )
      ..addStatusListener((status) {
        if (status == AnimationStatus.completed) widget.onComplete?.call();
      })
      ..forward();
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
          painter: _ConfettiPainter(
            t: _controller.value,
            particles: _particles,
            origin: widget.origin,
            radius: widget.radius,
          ),
          size: Size.infinite,
        ),
      ),
    );
  }
}

class _Particle {
  final double angle;
  final double speed;
  final double size;
  final Color color;
  const _Particle({
    required this.angle,
    required this.speed,
    required this.size,
    required this.color,
  });
}

class _ConfettiPainter extends CustomPainter {
  final double t;
  final List<_Particle> particles;
  final Offset origin;
  final double radius;

  const _ConfettiPainter({
    required this.t,
    required this.particles,
    required this.origin,
    required this.radius,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Quick out: ease-out distance, mild gravity pulls particles down toward end.
    final distance = radius * (1 - math.pow(1 - t, 2.0)).toDouble();
    final gravity = 8.0 * t * t;
    final fade = (1 - t).clamp(0.0, 1.0);

    for (final p in particles) {
      final dx = math.cos(p.angle) * distance * p.speed;
      final dy = math.sin(p.angle) * distance * p.speed + gravity;
      final pos = origin + Offset(dx, dy);
      final paint = Paint()
        ..color = p.color.withValues(alpha: fade)
        ..isAntiAlias = true;
      canvas.drawCircle(pos, p.size, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _ConfettiPainter old) =>
      old.t != t || old.origin != origin;
}
