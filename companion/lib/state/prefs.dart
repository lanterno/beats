import 'package:shared_preferences/shared_preferences.dart';

/// What the menu bar item shows while a timer runs.
enum MenuBarShows { timeAndProject, time, icon }

/// The settings people change in Settings, stored in SharedPreferences.
/// Each notification kind has its own switch; before they did, one switch
/// (`beats_notifications_enabled`) stood for all of them, and an install
/// that turned it off keeps them all off until each is turned on again.
class Prefs {
  static const notifyBrief = 'lifepete_notify_brief';
  static const notifySuggest = 'lifepete_notify_suggest';
  static const notifyDrift = 'lifepete_notify_drift';
  static const holdInFlow = 'lifepete_hold_in_flow';
  static const menuBar = 'lifepete_menu_bar';
  static const showInDock = 'lifepete_show_in_dock';
  static const _legacyAll = 'beats_notifications_enabled';

  final SharedPreferences _p;
  Prefs(this._p);

  static Future<Prefs> load() async => Prefs(await SharedPreferences.getInstance());

  bool _notify(String key) => _p.getBool(key) ?? _p.getBool(_legacyAll) ?? true;

  bool get briefOn => _notify(notifyBrief);
  bool get suggestOn => _notify(notifySuggest);
  bool get driftOn => _notify(notifyDrift);
  bool get holdingInFlow => _p.getBool(holdInFlow) ?? true;
  bool get dockVisible => _p.getBool(showInDock) ?? true;

  MenuBarShows get menuBarShows =>
      MenuBarShows.values.where((m) => m.name == _p.getString(menuBar)).firstOrNull ??
      MenuBarShows.timeAndProject;

  Future<void> setBool(String key, bool value) => _p.setBool(key, value);
  Future<void> setMenuBarShows(MenuBarShows m) => _p.setString(menuBar, m.name);
}

/// Whether to hold back notifications that can wait: the last ten minutes'
/// flow windows (scores 0–1) average 0.7 or more, over at least five of
/// them so a single good minute doesn't count as being in flow.
bool inFlow(List<double> lastTenMinutes) {
  if (lastTenMinutes.length < 5) return false;
  final avg = lastTenMinutes.reduce((a, b) => a + b) / lastTenMinutes.length;
  return avg >= 0.7;
}
