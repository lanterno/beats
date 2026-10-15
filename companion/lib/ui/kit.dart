import 'dart:math';

import 'package:flutter/material.dart';

import '../theme/sky.dart';

/// The shared surfaces every screen is built from: the sky behind them,
/// the panels on it, pill buttons, rings and small marks. Mirrors the web
/// app's `Panel`, pill controls and `SkyBackdrop`.

/// Phone width: the window is laid out for one thumb — a tab bar at the
/// foot instead of the sidebar, one column, tighter margins.
bool isCompact(BuildContext context) => MediaQuery.sizeOf(context).width < 600;

/// The padding a scrolling screen puts round its content: the margins for
/// its width, plus whatever the system and the phone's floating bars cover
/// (the shell adds those to MediaQuery's padding).
EdgeInsets pagePadding(BuildContext context) {
  final inset = MediaQuery.paddingOf(context);
  return isCompact(context)
      ? EdgeInsets.fromLTRB(16, inset.top + 12, 16, inset.bottom + 24)
      : EdgeInsets.fromLTRB(32, inset.top + 36, 32, inset.bottom + 40);
}

/// A project's hex colour (`#5B9CF6` or `5B9CF6`), or [fallback] when it is
/// missing or malformed.
Color projectColor(String? hex, {Color fallback = const Color(0xFF8A99A6)}) {
  if (hex == null) return fallback;
  final cleaned = hex.replaceFirst('#', '');
  if (cleaned.length != 6) return fallback;
  final value = int.tryParse(cleaned, radix: 16);
  return value == null ? fallback : Color(0xFF000000 | value);
}

/// The sky gradient every screen sits on, with the hills at its foot when
/// [hills] is set (pairing, focus).
class SkyBackdrop extends StatelessWidget {
  final Widget child;
  final bool hills;
  const SkyBackdrop({super.key, required this.child, this.hills = false});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: p.sky,
          stops: const [0, 0.34, 0.78, 1],
        ),
      ),
      child: hills
          ? Stack(children: [
              Positioned.fill(child: CustomPaint(painter: _HillsPainter(p.hills))),
              Positioned.fill(child: child),
            ])
          : child,
    );
  }
}

class _HillsPainter extends CustomPainter {
  final List<Color> colors;
  _HillsPainter(this.colors);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    // Three ridges, far to near, each lower and darker than the last.
    const ridges = [
      [0.84, 0.79, 0.83, 0.80],
      [0.90, 0.86, 0.91, 0.88],
      [0.955, 0.935, 0.96, 0.945],
    ];
    for (var i = 0; i < ridges.length; i++) {
      final r = ridges[i];
      final path = Path()
        ..moveTo(0, h * r[0])
        ..cubicTo(w * 0.18, h * r[1], w * 0.36, h * r[1], w * 0.5, h * r[2])
        ..cubicTo(w * 0.66, h * r[3], w * 0.84, h * r[1], w, h * r[3])
        ..lineTo(w, h)
        ..lineTo(0, h)
        ..close();
      canvas.drawPath(path, Paint()..color = colors[i]);
    }
  }

  @override
  bool shouldRepaint(_HillsPainter old) => old.colors != colors;
}

/// A rounded cloud-white surface. [raised] adds the longer shadow the web
/// app gives the one panel a screen is about (the timer, the brief).
class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;
  final bool raised;
  final Color? color;

  const Panel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(24),
    this.radius = 28,
    this.raised = false,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: color ?? p.panel,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: [
          const BoxShadow(color: Color(0x0F2B3A44), blurRadius: 2, offset: Offset(0, 1)),
          if (raised)
            const BoxShadow(color: Color(0x142B3A44), blurRadius: 32, offset: Offset(0, 12)),
        ],
      ),
      child: child,
    );
  }
}

enum SkyButtonKind { primary, secondary, dark, danger }

/// A pill button. [primary] is sunlight and there is one per screen at most.
class SkyButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final Widget? leading;
  final String? shortcut;
  final SkyButtonKind kind;
  final bool large;

  const SkyButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.leading,
    this.shortcut,
    this.kind = SkyButtonKind.secondary,
    this.large = false,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final (bg, fg) = switch (kind) {
      SkyButtonKind.primary => (p.sun, p.onSun),
      SkyButtonKind.secondary => (p.wash, p.ink),
      SkyButtonKind.dark => (p.ink, p.panel.withValues(alpha: 1)),
      SkyButtonKind.danger => (p.persimmonInk, Colors.white),
    };
    return FilledButton(
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        backgroundColor: bg,
        foregroundColor: fg,
        disabledBackgroundColor: bg.withValues(alpha: 0.5),
        disabledForegroundColor: fg.withValues(alpha: 0.6),
        shape: const StadiumBorder(),
        minimumSize: Size(0, large ? 50 : 40),
        padding: EdgeInsets.symmetric(horizontal: large ? 24 : 16),
        textStyle: SkyType.body(large ? 16 : 14, weight: FontWeight.w700),
        elevation: kind == SkyButtonKind.primary && large ? 2 : 0,
        shadowColor: p.sun.withValues(alpha: 0.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (leading != null) ...[leading!, const SizedBox(width: 10)],
          if (icon != null) ...[Icon(icon, size: large ? 18 : 16, color: fg), const SizedBox(width: 8)],
          Text(label),
          if (shortcut != null) ...[
            const SizedBox(width: 10),
            Text(shortcut!, style: SkyType.body(12).copyWith(color: fg.withValues(alpha: 0.7))),
          ],
        ],
      ),
    );
  }
}

/// A text-only action that reads as a link: "Undo", "Started earlier?".
class LinkButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final Color? color;
  final bool bold;
  const LinkButton({super.key, required this.label, required this.onPressed, this.color, this.bold = false});

  @override
  Widget build(BuildContext context) {
    final c = color ?? context.sky.ink;
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        foregroundColor: c,
        shape: const StadiumBorder(),
        minimumSize: const Size(0, 36),
        padding: const EdgeInsets.symmetric(horizontal: 10),
        textStyle: SkyType.body(14, weight: bold ? FontWeight.w700 : FontWeight.w400).copyWith(
          decoration: TextDecoration.underline,
          decorationColor: c.withValues(alpha: 0.35),
        ),
      ),
      child: Text(label),
    );
  }
}

/// A round icon-only button with a tooltip (which is also its accessible name).
class RoundIconButton extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final double size;
  const RoundIconButton({
    super.key,
    required this.icon,
    required this.tooltip,
    required this.onPressed,
    this.size = 36,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return IconButton(
      tooltip: tooltip,
      onPressed: onPressed,
      icon: Icon(icon, size: size * 0.48),
      style: IconButton.styleFrom(
        backgroundColor: p.wash,
        foregroundColor: p.ink,
        fixedSize: Size(size, size),
        minimumSize: Size(size, size),
      ),
    );
  }
}

class ProjectDot extends StatelessWidget {
  final Color color;
  final double size;
  const ProjectDot({super.key, required this.color, this.size = 10});

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(shape: BoxShape.circle, color: color),
      );
}

/// A small rounded label: shortcut hints, counts, "+1h 10m".
class Chip2 extends StatelessWidget {
  final String text;
  final Color? background;
  final Color? foreground;
  final bool bold;
  const Chip2(this.text, {super.key, this.background, this.foreground, this.bold = false});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: background ?? p.wash,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: SkyType.body(12, weight: bold ? FontWeight.w700 : FontWeight.w400)
            .copyWith(color: foreground ?? p.ink),
      ),
    );
  }
}

/// A ring that fills clockwise from twelve o'clock, with [child] inside.
class ProgressRing extends StatelessWidget {
  final double fraction;
  final double size;
  final double stroke;
  final Color color;
  final Color? track;
  final Widget? child;
  final String? semanticsLabel;

  /// Draws the sun where the arc ends, as the day ring in the logo does:
  /// a dot this many times the stroke wide, ringed in the panel's colour.
  final double? sun;

  const ProgressRing({
    super.key,
    required this.fraction,
    required this.color,
    this.size = 176,
    this.stroke = 14,
    this.track,
    this.child,
    this.semanticsLabel,
    this.sun,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticsLabel,
      child: SizedBox(
        width: size,
        height: size,
        child: CustomPaint(
          painter: _RingPainter(
            fraction: fraction.clamp(0.0, 1.0),
            color: color,
            track: track ?? context.sky.track,
            stroke: stroke,
            sun: sun,
            halo: context.sky.panel.withValues(alpha: 1),
          ),
          child: Center(child: child),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  final double fraction;
  final Color color;
  final Color track;
  final double stroke;
  final double? sun;
  final Color halo;
  _RingPainter({
    required this.fraction,
    required this.color,
    required this.track,
    required this.stroke,
    this.sun,
    this.halo = Colors.white,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final arc = rect.deflate(stroke / 2);
    final base = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(arc, 0, 2 * pi, false, base..color = track);
    if (fraction > 0) {
      canvas.drawArc(arc, -pi / 2, 2 * pi * fraction, false, base..color = color);
    }
    if (sun != null) {
      final a = -pi / 2 + 2 * pi * fraction;
      final r = arc.width / 2;
      final at = arc.center + Offset(cos(a), sin(a)) * r;
      final dot = stroke * sun! / 2;
      canvas.drawCircle(at, dot + stroke * 0.25, Paint()..color = halo);
      canvas.drawCircle(at, dot, Paint()..color = color);
    }
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.fraction != fraction ||
      old.color != color ||
      old.track != track ||
      old.sun != sun ||
      old.halo != halo;
}

/// A thin rounded bar filled to [fraction].
class ProgressBar extends StatelessWidget {
  final double fraction;
  final Color color;
  final double height;
  const ProgressBar({super.key, required this.fraction, required this.color, this.height = 8});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(999),
      child: SizedBox(
        height: height,
        child: ColoredBox(
          color: context.sky.track,
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            // The fill takes the bar's full height; only its width varies.
            child: FractionallySizedBox(
              widthFactor: fraction.clamp(0.0, 1.0),
              heightFactor: 1,
              child: DecoratedBox(
                decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(999)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Pill-shaped segmented control: one choice of a few.
class SegmentedPills<T> extends StatelessWidget {
  final List<(T, String)> options;
  final T value;
  final ValueChanged<T> onChanged;
  const SegmentedPills({super.key, required this.options, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.wash, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final (v, label) in options)
            Semantics(
              selected: v == value,
              button: true,
              child: TextButton(
                onPressed: () => onChanged(v),
                style: TextButton.styleFrom(
                  backgroundColor: v == value ? p.panel.withValues(alpha: 1) : Colors.transparent,
                  foregroundColor: p.ink,
                  shape: const StadiumBorder(),
                  minimumSize: const Size(0, 32),
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  textStyle: SkyType.body(13, weight: v == value ? FontWeight.w700 : FontWeight.w400),
                  elevation: v == value ? 1 : 0,
                  shadowColor: const Color(0x332B3A44),
                ),
                child: Text(label),
              ),
            ),
        ],
      ),
    );
  }
}

/// A heading for a panel, with an optional quiet line and trailing action.
class PanelHeading extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final double size;
  const PanelHeading(this.title, {super.key, this.subtitle, this.trailing, this.size = 19});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.end,
      spacing: 14,
      runSpacing: 4,
      children: [
        Semantics(header: true, child: Text(title, style: SkyType.display(size))),
        if (subtitle != null)
          Text(subtitle!, style: SkyType.body(13).copyWith(color: p.inkMuted)),
        ?trailing,
      ],
    );
  }
}

/// Centered message for a screen or panel with nothing to show yet.
class EmptyNote extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? body;
  final Widget? action;
  const EmptyNote({super.key, required this.icon, required this.title, this.body, this.action});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 30, color: p.inkMuted),
          const SizedBox(height: 10),
          Text(title, textAlign: TextAlign.center, style: SkyType.display(17)),
          if (body != null) ...[
            const SizedBox(height: 6),
            Text(body!, textAlign: TextAlign.center, style: SkyType.body(14).copyWith(color: p.inkMuted)),
          ],
          if (action != null) ...[const SizedBox(height: 14), action!],
        ],
      ),
    );
  }
}

/// The logo's day ring without its tile, drawn small in [color]: the
/// running project's mark in the phone's timer pill, as in the menu bar.
class RingGlyph extends StatelessWidget {
  final Color color;
  final double size;
  final Color? track;
  const RingGlyph({super.key, required this.color, this.size = 24, this.track});

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
        child: CustomPaint(
          size: Size.square(size),
          painter: _GlyphPainter(color, track ?? Colors.white.withValues(alpha: 0.25)),
        ),
      );
}

class _GlyphPainter extends CustomPainter {
  final Color color;
  final Color track;
  _GlyphPainter(this.color, this.track);

  @override
  void paint(Canvas canvas, Size size) {
    // shared/brand/favicon.svg's 32 grid: r11.5, stroke 4, sun r4.4.
    final k = size.width / 32;
    final c = Offset(16 * k, 16 * k);
    final r = 11.5 * k;
    final line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4 * k
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(c, r, line..color = track);
    const from = -pi / 2, sweep = pi * 4 / 3;
    canvas.drawArc(Rect.fromCircle(center: c, radius: r), from, sweep, false, line..color = color);
    canvas.drawCircle(c + Offset(cos(from + sweep), sin(from + sweep)) * r, 4.4 * k, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_GlyphPainter old) => old.color != color || old.track != track;
}
