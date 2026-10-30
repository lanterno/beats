import 'package:material_ui/material_ui.dart';

import '../services/offline_queue.dart';
import '../services/sync_story.dart';
import '../theme/sky.dart';
import 'kit.dart';

/// The dot beside a sync line: leaf when everything is saved, sun while
/// changes wait, persimmon when something is wrong.
class SyncDot extends StatelessWidget {
  final SyncTone tone;
  const SyncDot(this.tone, {super.key});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return ProjectDot(
      size: 8,
      color: switch (tone) {
        SyncTone.synced => p.leaf,
        SyncTone.waiting => p.sun,
        SyncTone.trouble => p.persimmon,
      },
    );
  }
}

/// The connection in one line, for the places without the sidebar's status
/// card: a phone's Today and the menu bar.
class SyncNote extends StatelessWidget {
  final SyncLine line;

  /// The text colour: muted ink on a panel, [SkyPalette.inkOnSky] on the sky.
  final Color? color;
  const SyncNote(this.line, {super.key, this.color});

  @override
  Widget build(BuildContext context) {
    final detail = line.detail;
    return Semantics(
      liveRegion: true,
      child: Row(children: [
        SyncDot(line.tone),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            detail == null ? line.title : '${line.title} · $detail',
            style: SkyType.body(13).copyWith(color: color ?? context.sky.inkMuted),
          ),
        ),
      ]),
    );
  }
}

/// Changes made offline that the server turned down when they synced: what
/// didn't save and why, until the person has read it.
class RefusedNote extends StatelessWidget {
  final List<RefusedWrite> refused;
  final String Function(String? projectId) nameOf;
  final VoidCallback onDismiss;
  const RefusedNote({super.key, required this.refused, required this.nameOf, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final p = context.sky;
    return Panel(
      radius: 20,
      padding: const EdgeInsets.fromLTRB(18, 14, 12, 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.sync_problem_rounded, size: 20, color: p.persimmonInk),
          const SizedBox(width: 10),
          Expanded(child: Text(refusedHeading(refused.length), style: SkyType.body(14, weight: FontWeight.w700))),
        ]),
        const SizedBox(height: 4),
        for (final r in refused)
          Padding(
            padding: const EdgeInsets.fromLTRB(30, 2, 6, 2),
            child: Text(describeRefusal(r, nameOf), style: SkyType.body(13, height: 1.5).copyWith(color: p.inkMuted)),
          ),
        Align(alignment: Alignment.centerRight, child: SkyButton(label: 'Got it', onPressed: onDismiss)),
      ]),
    );
  }
}
