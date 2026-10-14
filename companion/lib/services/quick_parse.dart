/// Reads what someone types into the quick-start palette:
///
///   kite                 start (or switch to) the best match, now
///   kite from 11:00      … from 11:00 today ("since" and "at" work too)
///   kite 9:30am          … the time can follow the name directly
///   spanish 25m ago      … from 25 minutes ago ("1h ago", "1h 30m ago")
///   stop                 stop what runs, now
///   stop at 17:30        … at 17:30 ("stop 10m ago" too)
///
/// Pure: the clock is passed in, so every case is testable.
library;

enum QuickVerb { start, stop }

class QuickCommand {
  final QuickVerb verb;

  /// The project words, for [QuickVerb.start]; empty for stop.
  final String query;

  /// When it takes effect; null means now.
  final DateTime? at;

  /// Why the time can't be used, e.g. it is still to come.
  final String? problem;

  const QuickCommand(this.verb, this.query, {this.at, this.problem});
}

final _clock = RegExp(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$', caseSensitive: false);
final _ago = RegExp(r'^((?:\d+\s*h)?\s*(?:\d+\s*m(?:in)?)?)\s+ago$', caseSensitive: false);
final _hm = RegExp(r'^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?$', caseSensitive: false);

QuickCommand parseQuick(String input, DateTime now) {
  var text = input.trim().replaceAll(RegExp(r'\s+'), ' ');
  final lower = text.toLowerCase();
  final verb = lower == 'stop' || lower.startsWith('stop ') ? QuickVerb.stop : QuickVerb.start;
  if (verb == QuickVerb.stop) text = text.substring(4).trim();

  DateTime? at;
  String? problem;

  // "<words> 25m ago"
  final words = text.split(' ');
  for (var i = 0; i < words.length && at == null; i++) {
    final tail = words.sublist(i).join(' ');
    final ago = _ago.firstMatch(tail);
    if (ago != null && ago.group(1)!.trim().isNotEmpty) {
      final d = _duration(ago.group(1)!);
      if (d != null) {
        at = now.subtract(d);
        text = words.sublist(0, i).join(' ');
      }
    }
  }

  // "<words> [from|since|at] 11:00"
  if (at == null) {
    final m = RegExp(r'^(.*?)(?:\s*\b(?:from|since|at)\b)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)$',
            caseSensitive: false)
        .firstMatch(text);
    if (m != null) {
      final clock = _clock.firstMatch(m.group(2)!.trim());
      // A bare number with no colon or am/pm after a name ("route 66") is
      // more likely part of the name than a time.
      final explicit = m.group(2)!.contains(':') ||
          RegExp(r'am|pm', caseSensitive: false).hasMatch(m.group(2)!) ||
          RegExp(r'\b(from|since|at)\s*$', caseSensitive: false)
              .hasMatch(text.substring(0, text.length - m.group(2)!.length));
      if (clock != null && explicit) {
        final t = _timeToday(clock, now);
        if (t != null) {
          at = t;
          text = m.group(1)!.trim();
          if (t.isAfter(now)) problem = '${_fmt(t)} hasn\'t happened yet';
        }
      }
    }
  }

  return QuickCommand(verb, verb == QuickVerb.stop ? '' : text.trim(), at: at, problem: problem);
}

Duration? _duration(String s) {
  final m = _hm.firstMatch(s.trim());
  if (m == null) return null;
  final h = int.tryParse(m.group(1) ?? '') ?? 0;
  final min = int.tryParse(m.group(2) ?? '') ?? 0;
  if (h == 0 && min == 0) return null;
  return Duration(hours: h, minutes: min);
}

DateTime? _timeToday(RegExpMatch m, DateTime now) {
  var h = int.parse(m.group(1)!);
  final min = int.tryParse(m.group(2) ?? '0') ?? 0;
  final ampm = m.group(3)?.toLowerCase();
  if (ampm != null) {
    if (h < 1 || h > 12) return null;
    if (ampm == 'pm' && h != 12) h += 12;
    if (ampm == 'am' && h == 12) h = 0;
  }
  if (h > 23 || min > 59) return null;
  return DateTime(now.year, now.month, now.day, h, min);
}

String _fmt(DateTime t) => '${t.hour}:${t.minute.toString().padLeft(2, '0')}';

/// Ranks [names] against [query]: a name that starts with it first, then one
/// with a word that does, then one containing it, then one with its letters
/// in order. Names that match none are left out. Returns indexes into
/// [names], best first; an empty query returns every index in order.
List<int> rankMatches(String query, List<String> names) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return List.generate(names.length, (i) => i);
  int? score(String name) {
    final n = name.toLowerCase();
    if (n.startsWith(q)) return 0;
    if (n.split(RegExp(r'[\s\-_/]+')).any((w) => w.startsWith(q))) return 1;
    if (n.contains(q)) return 2;
    var j = 0;
    for (final c in n.split('')) {
      if (j < q.length && c == q[j]) j++;
    }
    return j == q.length ? 3 : null;
  }

  final scored = <(int, int)>[];
  for (var i = 0; i < names.length; i++) {
    final s = score(names[i]);
    if (s != null) scored.add((s, i));
  }
  scored.sort((a, b) => a.$1 != b.$1 ? a.$1.compareTo(b.$1) : a.$2.compareTo(b.$2));
  return [for (final (_, i) in scored) i];
}
