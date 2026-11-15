// The global shortcuts' bindings (services/shortcuts.dart): what Settings
// stores and reads back, what it refuses, and what the native side is sent.
// The registration itself is macOS's (GlobalShortcuts.swift).

import 'dart:convert';

import 'package:beats_companion/services/shortcuts.dart';
import 'package:flutter_test/flutter_test.dart';

const c = KeyCombo.control, o = KeyCombo.option, s = KeyCombo.shift, m = KeyCombo.command;

void main() {
  group('KeyCombo', () {
    test('reads the way a menu does, the modifiers in macOS order', () {
      expect(const KeyCombo(0x23, m | s | o | c, 'P').label, '⌃⌥⇧⌘P');
      expect(const KeyCombo(0x31, m, 'Space').label, '⌘Space');
    });

    test('takes ⌃, ⌥ or ⌘ to be usable; ⇧ alone is typing', () {
      expect(const KeyCombo(0x11, c, 'T').usable, isTrue);
      expect(const KeyCombo(0x11, o, 'T').usable, isTrue);
      expect(const KeyCombo(0x11, m, 'T').usable, isTrue);
      expect(const KeyCombo(0x11, s, 'T').usable, isFalse);
      expect(const KeyCombo(0x11, 0, 'T').usable, isFalse);
    });

    test('is the same keys whatever the layout called them', () {
      // kVK_ANSI_Y is "Z" on a German keyboard.
      expect(const KeyCombo(0x10, m | o, 'Y'), const KeyCombo(0x10, m | o, 'Z'));
      expect(const KeyCombo(0x10, m | o, 'Y'), isNot(const KeyCombo(0x10, m, 'Y')));
    });
  });

  group('ShortcutBindings', () {
    test('nothing stored, or something unreadable, is the defaults', () {
      for (final stored in [null, '', 'not json', '[1, 2]', '{"palette": "⌃⌥T"}']) {
        final keys = ShortcutBindings.decode(stored);
        for (final a in ShortcutAction.values) {
          expect(keys[a], defaultShortcuts[a], reason: '$stored, ${a.name}');
        }
      }
      expect(ShortcutBindings.decode(null)[ShortcutAction.palette]?.label, '⌃⌥T');
    });

    test('reads back what it stored: a changed key, and one turned off', () {
      final changed = ShortcutBindings.decode(null)
          .withBinding(ShortcutAction.stop, const KeyCombo(0x01, c | m, 'S'))
          .withBinding(ShortcutAction.note, null);

      final read = ShortcutBindings.decode(changed.encode());

      expect(read, changed);
      expect(read[ShortcutAction.stop]?.label, '⌃⌘S');
      expect(read[ShortcutAction.note], isNull);
      expect(read[ShortcutAction.palette], defaultShortcuts[ShortcutAction.palette]);
    });

    test('a stored key that is no longer usable falls back to the default', () {
      final stored = jsonEncode({
        'stop': {'keyCode': 0x01, 'modifiers': s, 'key': 'S'},
      });
      expect(ShortcutBindings.decode(stored)[ShortcutAction.stop], defaultShortcuts[ShortcutAction.stop]);
    });

    test('an action stored before it existed starts off rather than take keys another one has', () {
      // Settings once gave Stop the keys Add to the note now defaults to,
      // then a later version added the note.
      final stored = jsonEncode({
        'palette': defaultShortcuts[ShortcutAction.palette]!.toJson(),
        'startLast': defaultShortcuts[ShortcutAction.startLast]!.toJson(),
        'stop': defaultShortcuts[ShortcutAction.note]!.toJson(),
      });
      final keys = ShortcutBindings.decode(stored);
      expect(keys[ShortcutAction.stop], defaultShortcuts[ShortcutAction.note]);
      expect(keys[ShortcutAction.note], isNull);
    });

    test('refuses keys another action has, or that leave out ⌃, ⌥ and ⌘', () {
      final keys = ShortcutBindings.decode(null);
      final palette = defaultShortcuts[ShortcutAction.palette]!;

      expect(keys.refusal(ShortcutAction.stop, palette), '⌃⌥T is already Quick start.');
      expect(keys.refusal(ShortcutAction.stop, const KeyCombo(0x01, s, 'S')), contains('Hold ⌃, ⌥ or ⌘'));
      // An action may keep its own keys.
      expect(keys.refusal(ShortcutAction.palette, palette), isNull);
      expect(keys.refusal(ShortcutAction.stop, const KeyCombo(0x01, c | m, 'S')), isNull);
    });

    test('sends the native side key codes and modifiers, and null for one turned off', () {
      final native = ShortcutBindings.decode(null).withBinding(ShortcutAction.note, null).toNative();

      expect(native.keys, ShortcutAction.values.map((a) => a.name));
      expect(native['palette'], {'keyCode': 0x11, 'modifiers': c | o});
      expect(native['stop'], {'keyCode': 0x2F, 'modifiers': c | o | m});
      expect(native['note'], isNull);
    });
  });
}
