/// Reads a week of `/api/biometrics` days into what the Body screen and
/// Today's body card say: the latest value of each measure, its series and
/// average, and a sentence for readiness.
library;

class BodyWeek {
  /// Days oldest first, as the API returns them (one per date and source).
  final List<Map<String, dynamic>> days;
  const BodyWeek(this.days);

  bool get isEmpty => days.isEmpty;

  /// The newest non-null value of [field], or null.
  num? latest(String field) {
    for (final d in days.reversed) {
      final v = d[field];
      if (v is num) return v;
    }
    return null;
  }

  /// Every non-null value of [field], oldest first.
  List<double> series(String field) => [
        for (final d in days)
          if (d[field] is num) (d[field] as num).toDouble(),
      ];

  double? average(String field) {
    final s = series(field);
    if (s.isEmpty) return null;
    return s.reduce((a, b) => a + b) / s.length;
  }

  /// Where the data comes from, as a person would name it: "Oura",
  /// "Oura and Fitbit".
  String? get sources {
    final names = <String>{
      for (final d in days)
        if (d['source'] is String && (d['source'] as String).isNotEmpty) _sourceName(d['source'] as String),
    }.toList();
    if (names.isEmpty) return null;
    if (names.length == 1) return names.first;
    return '${names.sublist(0, names.length - 1).join(', ')} and ${names.last}';
  }
}

String _sourceName(String s) => switch (s) {
      'oura' => 'Oura',
      'fitbit' => 'Fitbit',
      'healthkit' => 'Apple Health',
      'health_connect' => 'Health Connect',
      _ => s,
    };

/// One line on what a readiness score means for the day ahead.
String readinessLine(int score) {
  if (score >= 85) return 'Fully recovered. A good day for your hardest work.';
  if (score >= 70) return 'Recovered. A good day for a long block.';
  if (score >= 60) return 'Steady. Keep the blocks shorter and the breaks real.';
  return 'Running low. Plan lighter work and an early night.';
}

/// Sleep minutes as "7h 24m".
String formatSleep(num minutes) {
  final m = minutes.round();
  return '${m ~/ 60}h ${(m % 60).toString().padLeft(2, '0')}m';
}
