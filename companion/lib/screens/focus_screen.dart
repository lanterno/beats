import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/time_format.dart';
import '../state/timer_controller.dart';
import '../theme/sky.dart';
import '../ui/kit.dart';
import 'timer_actions.dart';

/// Focus mode: the timer as the only thing on screen, under the dusk sky
/// whatever hour the app is in — meant for a second display, or for when
/// the clock should be all there is. Shows the running session's elapsed
/// time, or the time of day when nothing runs. Esc or a click leaves;
/// ⌘. stops the timer.
class FocusScreen extends StatelessWidget {
  final TimerController timer;
  const FocusScreen({super.key, required this.timer});

  /// A phone or tablet, where the keyboard hints mean nothing. Read off the
  /// theme, so a phone-sized debug window counts.
  static bool _touch(BuildContext context) =>
      const [TargetPlatform.iOS, TargetPlatform.android].contains(Theme.of(context).platform);

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: buildSkyTheme(SkyPalette.dusk, Brightness.dark).copyWith(platform: Theme.of(context).platform),
      child: Builder(builder: (context) {
        final p = context.sky;
        return Focus(
          autofocus: true,
          onKeyEvent: (_, event) {
            if (event is! KeyDownEvent) return KeyEventResult.ignored;
            if (event.logicalKey == LogicalKeyboardKey.escape) {
              Navigator.of(context).maybePop();
              return KeyEventResult.handled;
            }
            final meta = HardwareKeyboard.instance.isMetaPressed || HardwareKeyboard.instance.isControlPressed;
            if (meta && event.logicalKey == LogicalKeyboardKey.period && timer.running) {
              TimerActions.stop(context, timer);
              return KeyEventResult.handled;
            }
            return KeyEventResult.ignored;
          },
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => Navigator.of(context).maybePop(),
            child: Scaffold(
              backgroundColor: Colors.transparent,
              body: SkyBackdrop(
                hills: true,
                child: Stack(children: [
                  // A low sun, just under the horizon.
                  Positioned.fill(
                    child: IgnorePointer(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: RadialGradient(
                            center: const Alignment(0, 1.05),
                            radius: 0.6,
                            colors: [p.sun.withValues(alpha: 0.45), p.sun.withValues(alpha: 0)],
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned.fill(
                    child: ListenableBuilder(
                      listenable: timer,
                      builder: (context, _) => ValueListenableBuilder(
                        valueListenable: timer.now,
                        builder: (context, now, _) => _Face(timer: timer, now: now),
                      ),
                    ),
                  ),
                  Positioned(
                    left: 24,
                    right: 24,
                    bottom: MediaQuery.paddingOf(context).bottom + 26,
                    // Rebuilt with the timer: launched straight into focus, the
                    // first frame comes before the first status read.
                    child: ListenableBuilder(
                      listenable: timer,
                      builder: (context, _) => _touch(context)
                          // A phone has no Esc or ⌘: a Stop to press, and a tap anywhere leaves.
                          ? Column(mainAxisSize: MainAxisSize.min, children: [
                              if (timer.running) ...[
                                SizedBox(
                                  width: double.infinity,
                                  height: 56,
                                  child: SkyButton(
                                    label: 'Stop',
                                    icon: Icons.stop_rounded,
                                    kind: SkyButtonKind.primary,
                                    large: true,
                                    onPressed: () => TimerActions.stop(context, timer),
                                  ),
                                ),
                                const SizedBox(height: 14),
                              ],
                              Text('Tap anywhere to leave',
                                  textAlign: TextAlign.center, style: SkyType.body(14).copyWith(color: p.ink)),
                            ])
                          : Text(
                              timer.running ? 'esc leave  ·  ⌘. stop  ·  ⌘K switch' : 'esc leave  ·  ⌘K start',
                              textAlign: TextAlign.center,
                              style: SkyType.body(14).copyWith(color: p.ink),
                            ),
                    ),
                  ),
                ]),
              ),
            ),
          ),
        );
      }),
    );
  }
}

class _Face extends StatelessWidget {
  final TimerController timer;
  final DateTime now;
  const _Face({required this.timer, required this.now});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    final project = timer.current;
    final running = timer.running && project != null;
    final big = running ? formatShortClock(timer.elapsed) : formatTimeOfDay(now);
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(32, 32, 32, 120),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (running)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
              decoration: BoxDecoration(
                color: p.ink.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                ProjectDot(color: project.color),
                const SizedBox(width: 10),
                Text(project.name, style: SkyType.body(17)),
              ]),
            ),
          const SizedBox(height: 16),
          Semantics(
            label: running ? 'Running for ${formatDuration(timer.elapsed)}' : 'The time is $big',
            excludeSemantics: true,
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(big, style: SkyType.figure(180).copyWith(letterSpacing: -4)),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            running ? 'since ${formatTimeOfDay(timer.since!)}' : 'Nothing running',
            style: SkyType.body(18).copyWith(color: p.inkOnSky),
          ),
          if (!running && !FocusScreen._touch(context)) ...[
            const SizedBox(height: 6),
            Text('⌘K to start', style: SkyType.body(15).copyWith(color: p.inkMuted)),
          ],
        ]),
      ),
    );
  }
}
