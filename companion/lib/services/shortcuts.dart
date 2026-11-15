import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'status_menu.dart';

/// What a global shortcut on the Mac does (companion/README.md § Shortcuts).
enum ShortcutAction {
  palette('Quick start', 'Opens the palette from any app'),
  startLast('Start the last project', 'Starts what you tracked last'),
  stop('Stop', 'Stops the running timer'),
  note('Add to the note', 'A line on the running session’s note');

  final String title;
  final String subtitle;
  const ShortcutAction(this.title, this.subtitle);
}

/// A key and the modifiers held with it. [keyCode] is macOS's (`kVK_*`), a
/// place on the keyboard whatever the layout; [key] is how to show it, read
/// off the layout when the combination was recorded.
@immutable
class KeyCombo {
  static const control = 1;
  static const option = 2;
  static const shift = 4;
  static const command = 8;

  final int keyCode;
  final int modifiers;
  final String key;
  const KeyCombo(this.keyCode, this.modifiers, this.key);

  /// As a menu shows it, the modifiers in macOS's order: ⌃⌥⇧⌘.
  String get label => [
        if (modifiers & control != 0) '⌃',
        if (modifiers & option != 0) '⌥',
        if (modifiers & shift != 0) '⇧',
        if (modifiers & command != 0) '⌘',
        key,
      ].join();

  /// Held with ⌃, ⌥ or ⌘. A key alone, or with ⇧ alone, is typing: taken
  /// from every app, it could be typed in none.
  bool get usable => modifiers & (control | option | command) != 0;

  Map<String, Object> toJson() => {'keyCode': keyCode, 'modifiers': modifiers, 'key': key};

  static KeyCombo? fromJson(Object? json) {
    if (json is! Map) return null;
    final code = json['keyCode'], mods = json['modifiers'], key = json['key'];
    if (code is! int || mods is! int || key is! String || key.isEmpty) return null;
    return KeyCombo(code, mods, key);
  }

  // The label is how it reads on one layout, not what it is.
  @override
  bool operator ==(Object other) => other is KeyCombo && other.keyCode == keyCode && other.modifiers == modifiers;

  @override
  int get hashCode => Object.hash(keyCode, modifiers);

  @override
  String toString() => label;
}

const _ctrlOpt = KeyCombo.control | KeyCombo.option;
const _ctrlOptCmd = KeyCombo.control | KeyCombo.option | KeyCombo.command;

/// The keys #305 named; ⌃⌥T opened the palette before any was configurable.
const defaultShortcuts = <ShortcutAction, KeyCombo>{
  ShortcutAction.palette: KeyCombo(0x11, _ctrlOpt, 'T'), // kVK_ANSI_T
  ShortcutAction.startLast: KeyCombo(0x23, _ctrlOptCmd, 'P'), // kVK_ANSI_P
  ShortcutAction.stop: KeyCombo(0x2F, _ctrlOptCmd, '.'), // kVK_ANSI_Period
  ShortcutAction.note: KeyCombo(0x2D, _ctrlOptCmd, 'N'), // kVK_ANSI_N
};

/// Every action's binding: what Settings stored, else its default; null is
/// off.
@immutable
class ShortcutBindings {
  static const prefsKey = 'lifepete_shortcuts';

  final Map<ShortcutAction, KeyCombo?> _bindings;
  const ShortcutBindings._(this._bindings);

  /// [stored] as [encode] wrote it: a JSON object from an action's name to
  /// its combination, or to null when it is off. An action it leaves out,
  /// or gives something unreadable or [KeyCombo.usable] would refuse, keeps
  /// its default, unless another action now holds that combination: an
  /// action added after the rest were set starts off rather than take one.
  factory ShortcutBindings.decode(String? stored) {
    Object? json;
    try {
      json = stored == null ? null : jsonDecode(stored);
    } on FormatException {
      json = null;
    }
    final set = <ShortcutAction, KeyCombo?>{};
    if (json is Map) {
      for (final a in ShortcutAction.values) {
        if (!json.containsKey(a.name)) continue;
        final value = json[a.name];
        final combo = KeyCombo.fromJson(value);
        if (value == null) {
          set[a] = null;
        } else if (combo != null && combo.usable) {
          set[a] = combo;
        }
      }
    }
    final taken = set.values.whereType<KeyCombo>().toSet();
    return ShortcutBindings._({
      for (final a in ShortcutAction.values)
        a: set.containsKey(a)
            ? set[a]
            : taken.contains(defaultShortcuts[a])
                ? null
                : defaultShortcuts[a],
    });
  }

  String encode() => jsonEncode({for (final a in ShortcutAction.values) a.name: _bindings[a]?.toJson()});

  KeyCombo? operator [](ShortcutAction a) => _bindings[a];

  ShortcutBindings withBinding(ShortcutAction a, KeyCombo? combo) => ShortcutBindings._({..._bindings, a: combo});

  /// The action other than [except] that [combo] already does, if any.
  ShortcutAction? holder(KeyCombo combo, {ShortcutAction? except}) =>
      ShortcutAction.values.where((a) => a != except && _bindings[a] == combo).firstOrNull;

  /// Why [combo] cannot be [action]'s, in words for Settings; null when it
  /// can.
  String? refusal(ShortcutAction action, KeyCombo combo) {
    if (!combo.usable) return 'Hold ⌃, ⌥ or ⌘ with the key, so it stays free for typing.';
    final other = holder(combo, except: action);
    if (other != null) return '${combo.label} is already ${other.title}.';
    return null;
  }

  /// What the native side registers (GlobalShortcuts.swift): each action's
  /// name to its key code and modifiers, or to null when it is off.
  Map<String, Object?> toNative() => {
        for (final a in ShortcutAction.values)
          a.name: switch (_bindings[a]) {
            null => null,
            final c => {'keyCode': c.keyCode, 'modifiers': c.modifiers},
          },
      };

  static Future<ShortcutBindings> load() async =>
      ShortcutBindings.decode((await SharedPreferences.getInstance()).getString(prefsKey));

  Future<void> save() async => (await SharedPreferences.getInstance()).setString(prefsKey, encode());

  @override
  bool operator ==(Object other) => other is ShortcutBindings && mapEquals(other._bindings, _bindings);

  @override
  int get hashCode => Object.hashAll(ShortcutAction.values.map((a) => _bindings[a]));
}

/// The shortcuts in force in this window's engine, and the actions macOS
/// refused because another app holds their combination. Settings reads
/// both; [apply] is the one way either changes.
class ShortcutsInForce {
  static final shortcuts = ValueNotifier<ShortcutBindings>(ShortcutBindings.decode(null));
  static final refused = ValueNotifier<Set<ShortcutAction>>(const {});

  /// Registers [s] with macOS and keeps it; a no-op off macOS.
  static Future<void> apply(ShortcutBindings s) async {
    if (!Platform.isMacOS) return;
    final names = await StatusMenu.setShortcuts(s.toNative());
    shortcuts.value = s;
    refused.value = {
      for (final a in ShortcutAction.values)
        if (names.contains(a.name)) a,
    };
  }
}
