import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Which hour the app is drawn in. `system` follows macOS's appearance:
/// Light is the afternoon, Dark is dusk.
enum Hour { afternoon, dusk, system }

/// The stored hour, read once at launch and written from Settings.
/// A stored value that is none of the three reads as [Hour.system].
class HourController extends ValueNotifier<Hour> {
  static const _key = 'lifepete_hour';

  HourController() : super(Hour.system);

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    value = hourFromName(prefs.getString(_key));
  }

  Future<void> set(Hour hour) async {
    value = hour;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, hour.name);
  }

  ThemeMode get themeMode => switch (value) {
        Hour.afternoon => ThemeMode.light,
        Hour.dusk => ThemeMode.dark,
        Hour.system => ThemeMode.system,
      };
}

Hour hourFromName(String? name) =>
    Hour.values.where((h) => h.name == name).firstOrNull ?? Hour.system;
