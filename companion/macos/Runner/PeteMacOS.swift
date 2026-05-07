import Cocoa
import FlutterMacOS

/// Bridges the Pete Dart layer to macOS-only AppKit features the
/// `window_manager` and `system_tray` plugins don't cover. Method names
/// are namespaced by surface (`dock.setBadge`) so future bridges can
/// land here without colliding.
final class PeteMacOS {
  static let channelName = "pete/macos"

  private weak var registrar: FlutterPluginRegistrar?

  init(registrar: FlutterPluginRegistrar) {
    self.registrar = registrar
    let channel = FlutterMethodChannel(
      name: PeteMacOS.channelName,
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

    default:
      result(FlutterMethodNotImplemented)
    }
  }
}
