/// What the companion says about its connection and the changes made
/// offline (docs/companion-offline.md): the sidebar's status card, the
/// line on a phone's Today and in the menu bar, Today's note of what the
/// server refused, and the warning before unpairing drops what waits.
library;

import 'offline_queue.dart';
import 'time_format.dart';

/// How a sync line is marked: leaf when everything is saved, sun for a
/// wait that ends by itself, persimmon when something is wrong.
enum SyncTone { synced, waiting, trouble }

typedef SyncLine = ({String title, String? detail, SyncTone tone});

String _changes(int n) => n == 1 ? '1 change' : '$n changes';

/// The connection in a title and an optional detail. [failing] is a read
/// with nothing kept to fall back on (the timer couldn't be read at all).
SyncLine describeSync({required bool online, required bool syncing, required int pending, required bool failing}) {
  if (syncing && pending > 0) {
    return (title: 'Syncing', detail: '${_changes(pending)} on the way', tone: SyncTone.waiting);
  }
  if (!online && pending > 0) {
    return (title: 'Offline', detail: '${_changes(pending)} waiting to sync', tone: SyncTone.waiting);
  }
  if (failing) return (title: 'Can\'t reach the server', detail: null, tone: SyncTone.trouble);
  if (!online) return (title: 'Offline', detail: 'Changes will sync later', tone: SyncTone.waiting);
  if (pending > 0) return (title: '${_changes(pending)} waiting to sync', detail: null, tone: SyncTone.waiting);
  return (title: 'Synced', detail: null, tone: SyncTone.synced);
}

/// The heading over the changes the server refused.
String refusedHeading(int n) => n == 1 ? 'A change made offline didn\'t sync' : '$n changes made offline didn\'t sync';

/// One refused change: what didn't save, then why, in the server's words
/// where it gave none of its own codes. "Stopping Northwind at 10:30 wasn't
/// saved. The timer had changed on another device."
String describeRefusal(RefusedWrite r, String Function(String? projectId) nameOf) {
  final b = r.body;
  final expected = b['expected'] is Map ? b['expected'] as Map : const {};
  String t(Object? iso) {
    final at = iso is String ? DateTime.tryParse(iso) : null;
    return at == null ? '?' : formatTimeOfDay(at);
  }

  final what = switch (r.kind) {
    WriteKind.start => 'Starting ${nameOf(b['project_id'] as String?)} at ${t(b['time'])}',
    WriteKind.stop => 'Stopping ${nameOf(expected['project_id'] as String?)} at ${t(b['time'])}',
    WriteKind.log => 'Logging ${nameOf(b['project_id'] as String?)} from ${t(b['start'])} to ${t(b['end'])}',
    WriteKind.edit when b['end'] == null =>
      'Moving the start of ${nameOf(b['project_id'] as String?)} to ${t(b['start'])}',
    WriteKind.edit => 'Changing the ${nameOf(expected['project_id'] as String?)} session '
        'from ${t(expected['start'])} to ${t(expected['end'])}',
  };
  final why = switch (r.code) {
    'TIMER_CHANGED' => 'The timer had changed on another device.',
    'BEAT_CHANGED' => 'That session had changed elsewhere.',
    _ when r.status == 404 => 'That session was deleted elsewhere.',
    _ => _sentence(r.detail),
  };
  return '$what wasn\'t saved. $why';
}

String _sentence(String s) {
  final t = s.trim();
  if (t.isEmpty) return 'The server turned it down.';
  final first = t[0].toUpperCase() + t.substring(1);
  return RegExp(r'[.!?]$').hasMatch(first) ? first : '$first.';
}

/// Said before unpairing while changes wait: unpairing forgets them.
String? unpairWarning(int pending) => pending == 0
    ? null
    : '${pending == 1 ? '1 change made offline hasn\'t' : '$pending changes made offline haven\'t'} '
        'reached the server yet. Unpairing now drops ${pending == 1 ? 'it' : 'them'}.';
