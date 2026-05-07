import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/beats_theme.dart';

/// Full-bleed, near-black clock face. The "Monastic" mode from the Pete
/// macOS roadmap — meant to be left running on a docked secondary
/// display, or invoked when the user wants the timer to be the only
/// thing on screen.
///
/// Renders the running session's elapsed time when one is active;
/// otherwise the wall clock. ESC, ⌘., or a tap anywhere exits.
class MonasticScreen extends StatefulWidget {
  /// Optional running-timer context. When non-null, the screen shows
  /// elapsed time and a project dot; when null, it falls back to the
  /// wall clock (the screen still works as a "I'm AFK" surface).
  final DateTime? startTime;
  final String? projectName;
  final List<int>? projectColor;

  const MonasticScreen({
    super.key,
    this.startTime,
    this.projectName,
    this.projectColor,
  });

  @override
  State<MonasticScreen> createState() => _MonasticScreenState();
}

class _MonasticScreenState extends State<MonasticScreen>
    with SingleTickerProviderStateMixin {
  Timer? _ticker;
  late AnimationController _pulse;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _now = DateTime.now());
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dotRgb = widget.projectColor ?? const [212, 149, 42];
    final dotColor = Color.fromARGB(255, dotRgb[0], dotRgb[1], dotRgb[2]);

    final showElapsed = widget.startTime != null;
    final time = showElapsed
        ? _now.toUtc().difference(widget.startTime!.toUtc())
        : _wallDuration(_now);
    final h = time.inHours;
    final m = time.inMinutes.remainder(60);
    final s = time.inSeconds.remainder(60);
    final hh = showElapsed ? h.toString().padLeft(2, '0') : _wallHour(_now);
    final mm = m.toString().padLeft(2, '0');
    final ss = s.toString().padLeft(2, '0');

    return Focus(
      autofocus: true,
      onKeyEvent: (_, event) {
        if (event is KeyDownEvent &&
            (event.logicalKey == LogicalKeyboardKey.escape ||
                event.logicalKey == LogicalKeyboardKey.period)) {
          Navigator.of(context).maybePop();
          return KeyEventResult.handled;
        }
        return KeyEventResult.ignored;
      },
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => Navigator.of(context).maybePop(),
        child: Scaffold(
          backgroundColor: Colors.black,
          body: SafeArea(
            child: Stack(
              children: [
                // ── Massive clock face ──
                Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.baseline,
                        textBaseline: TextBaseline.alphabetic,
                        children: [
                          _MonkDigit(value: hh),
                          _MonkColon(),
                          _MonkDigit(value: mm),
                          _MonkColon(),
                          _MonkDigit(
                            value: ss,
                            color: BeatsColors.textPrimary.withValues(alpha: 0.35),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

                // ── Project dot + name (only when running) ──
                if (showElapsed && widget.projectName != null)
                  Positioned(
                    top: 32,
                    left: 32,
                    child: AnimatedBuilder(
                      animation: _pulse,
                      builder: (_, _) => Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: dotColor.withValues(
                                alpha: 0.4 + _pulse.value * 0.6,
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: dotColor.withValues(
                                    alpha: 0.20 + _pulse.value * 0.30,
                                  ),
                                  blurRadius: 12 + _pulse.value * 8,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(
                            widget.projectName!,
                            style: BeatsType.label.copyWith(
                              letterSpacing: 3,
                              color: BeatsColors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                // ── Faint exit hint ──
                Positioned(
                  bottom: 24,
                  right: 32,
                  child: Text(
                    'ESC TO EXIT',
                    style: BeatsType.label.copyWith(
                      letterSpacing: 4,
                      fontSize: 10,
                      color: BeatsColors.textTertiary.withValues(alpha: 0.4),
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

  /// Wall clock as a Duration since midnight — keeps the same digit
  /// machinery as the elapsed branch.
  static Duration _wallDuration(DateTime t) =>
      Duration(hours: t.hour, minutes: t.minute, seconds: t.second);

  static String _wallHour(DateTime t) => t.hour.toString().padLeft(2, '0');
}

class _MonkDigit extends StatelessWidget {
  final String value;
  final Color? color;
  const _MonkDigit({required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    return Text(
      value,
      style: GoogleFonts.jetBrainsMono(
        fontSize: 220,
        fontWeight: FontWeight.w200,
        height: 1,
        color: color ?? BeatsColors.textPrimary,
        fontFeatures: [const FontFeature.tabularFigures()],
      ),
    );
  }
}

class _MonkColon extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Text(
        ':',
        style: GoogleFonts.jetBrainsMono(
          fontSize: 220,
          fontWeight: FontWeight.w100,
          height: 1,
          color: BeatsColors.textPrimary.withValues(alpha: 0.18),
        ),
      ),
    );
  }
}
