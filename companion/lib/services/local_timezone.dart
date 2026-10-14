import 'package:flutter_timezone/flutter_timezone.dart';

String? _cached;

/// This machine's IANA timezone ("Africa/Cairo"), read once; null where the
/// platform won't say, in which case the API reads days in UTC.
Future<String?> localTimezone() async {
  if (_cached != null) return _cached;
  try {
    return _cached = (await FlutterTimezone.getLocalTimezone()).identifier;
  } catch (_) {
    return null;
  }
}
