import Cocoa
import FlutterMacOS
import ServiceManagement

/// Bridges the companion's Dart layer to macOS-only AppKit features the
/// `window_manager` and `system_tray` plugins don't cover: the Dock badge
/// and icon, and opening at login. Method names
/// are namespaced by surface (`dock.setBadge`) so future bridges can
/// land here without colliding.
final class MacAmbientBridge {
  static let channelName = "companion/macos"

  private weak var registrar: FlutterPluginRegistrar?

  init(registrar: FlutterPluginRegistrar) {
    self.registrar = registrar
    let channel = FlutterMethodChannel(
      name: MacAmbientBridge.channelName,
      binaryMessenger: registrar.messenger
    )
    channel.setMethodCallHandler { [weak self] call, result in
      self?.handle(call: call, result: result)
    }
  }

  private func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "dock.setBadge":
      let label = (call.arguments as? [String: Any])?["label"] as? String
      DispatchQueue.main.async {
        NSApp.dockTile.badgeLabel = (label?.isEmpty ?? true) ? nil : label
      }
      result(nil)

    case "login.isEnabled":
      if #available(macOS 13.0, *) {
        result(SMAppService.mainApp.status == .enabled)
      } else {
        result(nil)  // Not offered before macOS 13; Settings hides the row.
      }

    case "login.setEnabled":
      let enabled = (call.arguments as? [String: Any])?["enabled"] as? Bool ?? false
      guard #available(macOS 13.0, *) else {
        result(FlutterError(code: "UNSUPPORTED", message: "Needs macOS 13 or later", details: nil))
        return
      }
      do {
        if enabled {
          try SMAppService.mainApp.register()
        } else {
          try SMAppService.mainApp.unregister()
        }
        result(SMAppService.mainApp.status == .enabled)
      } catch {
        result(FlutterError(code: "LOGIN_ITEM", message: error.localizedDescription, details: nil))
      }

    case "dock.setVisible":
      let visible = (call.arguments as? [String: Any])?["visible"] as? Bool ?? true
      DispatchQueue.main.async {
        // An accessory app has no Dock icon and no app menu; it lives in
        // the menu bar. Switching policy deactivates the app, so bring the
        // window back to the front when it was on screen.
        let frontWindow = NSApp.keyWindow ?? NSApp.mainWindow
        NSApp.setActivationPolicy(visible ? .regular : .accessory)
        if let w = frontWindow {
          NSApp.activate(ignoringOtherApps: true)
          w.makeKeyAndOrderFront(nil)
        }
      }
      result(nil)

    default:
      result(FlutterMethodNotImplemented)
    }
  }
}
