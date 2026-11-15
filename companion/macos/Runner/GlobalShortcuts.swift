import Carbon.HIToolbox
import Cocoa

/// The app's global shortcuts (companion/README.md § Shortcuts): Carbon hot
/// keys, which need no Accessibility permission, one per action. The bindings
/// are the Dart side's (`lib/services/shortcuts.dart`), sent whole over
/// `companion/menubar`; this registers them and says which macOS refused
/// because another app holds the combination.
final class GlobalShortcuts {
  /// What a shortcut does. The raw values are the names Dart sends.
  enum Action: String, CaseIterable {
    case palette, startLast, stop, note

    var id: UInt32 { UInt32(Action.allCases.firstIndex(of: self)! + 1) }
  }

  /// A key code (`kVK_*`, a position on the keyboard) and Carbon modifiers.
  struct Binding: Equatable {
    let keyCode: UInt32
    let modifiers: UInt32
  }

  static let signature = OSType(0x4C50_4554)  // 'LPET'

  // The modifier bits Dart uses (KeyCombo in shortcuts.dart).
  private static let dartControl = 1
  private static let dartOption = 2
  private static let dartShift = 4
  private static let dartCommand = 8

  var onPress: ((Action) -> Void)?
  private var bindings: [Action: Binding] = [:]
  private var refs: [Action: EventHotKeyRef] = [:]
  private var monitor: Any?
  private var recorded: (([String: Any]?) -> Void)?

  init() {
    var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    let me = Unmanaged.passUnretained(self).toOpaque()
    InstallEventHandler(GetApplicationEventTarget(), { _, event, userData in
      guard let event, let userData else { return OSStatus(eventNotHandledErr) }
      var hotKey = EventHotKeyID()
      let status = GetEventParameter(
        event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
        MemoryLayout<EventHotKeyID>.size, nil, &hotKey)
      guard status == noErr, hotKey.signature == GlobalShortcuts.signature,
        let action = Action.allCases.first(where: { $0.id == hotKey.id })
      else { return OSStatus(eventNotHandledErr) }
      let shortcuts = Unmanaged<GlobalShortcuts>.fromOpaque(userData).takeUnretainedValue()
      DispatchQueue.main.async { shortcuts.onPress?(action) }
      return noErr
    }, 1, &spec, me, nil)
  }

  /// Replaces every registration with [bindings] and returns the actions
  /// macOS refused. While a recording is open nothing is registered; the
  /// bindings take effect when it ends.
  func set(_ bindings: [Action: Binding]) -> [Action] {
    self.bindings = bindings
    return monitor == nil ? register() : []
  }

  /// [set]'s argument from Dart's: each action's name to `{keyCode,
  /// modifiers}`, or to null when it is off. Unknown names are skipped.
  static func bindings(fromDart map: [String: Any]) -> [Action: Binding] {
    var out: [Action: Binding] = [:]
    for (name, value) in map {
      guard let action = Action(rawValue: name), let combo = value as? [String: Any],
        let keyCode = combo["keyCode"] as? Int, let modifiers = combo["modifiers"] as? Int
      else { continue }
      out[action] = Binding(keyCode: UInt32(keyCode), modifiers: carbon(fromDart: modifiers))
    }
    return out
  }

  // Exclusive, so a combination another app has registered is refused here
  // rather than shared, and Settings can say so.
  private func register() -> [Action] {
    unregister()
    var refused: [Action] = []
    for action in Action.allCases {
      guard let b = bindings[action] else { continue }
      var ref: EventHotKeyRef?
      let status = RegisterEventHotKey(
        b.keyCode, b.modifiers, EventHotKeyID(signature: Self.signature, id: action.id),
        GetApplicationEventTarget(), OptionBits(kEventHotKeyExclusive), &ref)
      if status == noErr, let ref {
        refs[action] = ref
      } else {
        refused.append(action)
      }
    }
    return refused
  }

  private func unregister() {
    for ref in refs.values { UnregisterEventHotKey(ref) }
    refs.removeAll()
  }

  // MARK: Recording

  /// Hands [done] the next key pressed in this app — `{keyCode, modifiers,
  /// key}`, `key` being how to show it — or nil when Esc alone cancels, or
  /// [cancelRecording] does. Every shortcut is off meanwhile, so pressing
  /// the one being replaced records it rather than firing it, and the press
  /// goes nowhere else: ⌘Q is recorded, not quit.
  func record(_ done: @escaping ([String: Any]?) -> Void) {
    cancelRecording()
    unregister()
    recorded = done
    monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
      guard let self else { return event }
      let flags = event.modifierFlags.intersection([.control, .option, .shift, .command])
      if Int(event.keyCode) == kVK_Escape, flags.isEmpty {
        self.finishRecording(nil)
      } else {
        self.finishRecording([
          "keyCode": Int(event.keyCode),
          "modifiers": Self.dart(fromFlags: flags),
          "key": Self.label(of: event),
        ])
      }
      return nil
    }
  }

  func cancelRecording() {
    finishRecording(nil)
  }

  private func finishRecording(_ value: [String: Any]?) {
    guard let monitor else { return }
    NSEvent.removeMonitor(monitor)
    self.monitor = nil
    let done = recorded
    recorded = nil
    _ = register()
    done?(value)
  }

  // MARK: Translations

  private static func carbon(fromDart m: Int) -> UInt32 {
    var out = 0
    if m & dartControl != 0 { out |= controlKey }
    if m & dartOption != 0 { out |= optionKey }
    if m & dartShift != 0 { out |= shiftKey }
    if m & dartCommand != 0 { out |= cmdKey }
    return UInt32(out)
  }

  private static func dart(fromFlags f: NSEvent.ModifierFlags) -> Int {
    var out = 0
    if f.contains(.control) { out |= dartControl }
    if f.contains(.option) { out |= dartOption }
    if f.contains(.shift) { out |= dartShift }
    if f.contains(.command) { out |= dartCommand }
    return out
  }

  /// The key as a menu shows it: a symbol or name for the keys that have
  /// one, else the character it types with no modifier on the current
  /// layout, so ⇧⌘1 reads "1", not "!".
  private static func label(of event: NSEvent) -> String {
    if let named = named[Int(event.keyCode)] { return named }
    let typed = event.characters(byApplyingModifiers: []) ?? event.charactersIgnoringModifiers ?? ""
    return typed.uppercased()
  }

  private static let named: [Int: String] = {
    var names: [Int: String] = [
      kVK_Space: "Space", kVK_Return: "↩", kVK_ANSI_KeypadEnter: "⌤", kVK_Tab: "⇥",
      kVK_Delete: "⌫", kVK_ForwardDelete: "⌦", kVK_Escape: "⎋",
      kVK_LeftArrow: "←", kVK_RightArrow: "→", kVK_UpArrow: "↑", kVK_DownArrow: "↓",
      kVK_Home: "↖", kVK_End: "↘", kVK_PageUp: "⇞", kVK_PageDown: "⇟",
    ]
    let functionKeys = [
      kVK_F1, kVK_F2, kVK_F3, kVK_F4, kVK_F5, kVK_F6, kVK_F7, kVK_F8, kVK_F9, kVK_F10,
      kVK_F11, kVK_F12, kVK_F13, kVK_F14, kVK_F15, kVK_F16, kVK_F17, kVK_F18, kVK_F19, kVK_F20,
    ]
    for (i, code) in functionKeys.enumerated() { names[code] = "F\(i + 1)" }
    return names
  }()
}
