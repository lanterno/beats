import Carbon.HIToolbox
import Cocoa
import FlutterMacOS

/// LifePete's menu bar item and the popover under it.
///
/// The item's title and icon are set by the main window's Dart side
/// (`lib/services/menu_bar.dart`) over `companion/menubar`. A click opens
/// an NSPopover whose content is a second Flutter engine running the
/// `popoverMain` entrypoint (`lib/popover/popover_app.dart`), so the popover
/// is real Flutter UI with the app's look, and it talks back over
/// `companion/popover`. The engine starts on the first click, not at launch.
///
/// ⌃⌥T, from any app, opens the popover on its quick-start field. It is a
/// Carbon hot key, which needs no Accessibility permission. (The design's
/// ⌥⌘Space is macOS's Finder search.)
final class StatusItemController: NSObject, NSPopoverDelegate {
  static let mainChannelName = "companion/menubar"
  static let popoverChannelName = "companion/popover"

  private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
  private let popover = NSPopover()
  private let mainChannel: FlutterMethodChannel
  private var popoverEngine: FlutterEngine?
  private var popoverChannel: FlutterMethodChannel?
  private weak var window: NSWindow?
  private var hotKey: EventHotKeyRef?

  init(mainMessenger: FlutterBinaryMessenger, window: NSWindow) {
    mainChannel = FlutterMethodChannel(name: Self.mainChannelName, binaryMessenger: mainMessenger)
    self.window = window
    super.init()

    popover.behavior = .transient
    popover.animates = true
    popover.delegate = self
    popover.contentSize = NSSize(width: 360, height: 540)

    if let button = statusItem.button {
      button.target = self
      button.action = #selector(clicked(_:))
      button.sendAction(on: [.leftMouseUp, .rightMouseUp])
      button.imagePosition = .imageLeading
    }
    // Hidden until the Dart side reports a paired device.
    statusItem.isVisible = false

    mainChannel.setMethodCallHandler { [weak self] call, result in
      self?.handleMain(call, result)
    }
    registerHotKey()
    #if DEBUG
      // `open --env LIFEPETE_POPOVER=panel|palette …` opens the popover once
      // the item is up, so it can be looked at without clicking.
      if let mode = ProcessInfo.processInfo.environment["LIFEPETE_POPOVER"] {
        debugShow(mode: mode, attempts: 30)
      }
    #endif
  }

  #if DEBUG
    private func debugShow(mode: String, attempts: Int) {
      DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
        guard let self else { return }
        if self.statusItem.isVisible {
          self.show(mode: mode)
        } else if attempts > 0 {
          self.debugShow(mode: mode, attempts: attempts - 1)
        }
      }
    }
  #endif

  // MARK: Main window → menu bar

  private func handleMain(_ call: FlutterMethodCall, _ result: @escaping FlutterResult) {
    let args = call.arguments as? [String: Any] ?? [:]
    switch call.method {
    case "status.update":
      statusItem.isVisible = args["visible"] as? Bool ?? true
      if let button = statusItem.button {
        let title = args["title"] as? String ?? ""
        button.title = title.isEmpty ? "" : " \(title)"
        button.toolTip = args["tooltip"] as? String
        if let path = args["imagePath"] as? String, let image = NSImage(contentsOfFile: path) {
          image.size = NSSize(width: 18, height: 18)
          // A template is drawn in the menu bar's own colour from its alpha.
          image.isTemplate = args["template"] as? Bool ?? false
          button.image = image
        }
      }
      if !statusItem.isVisible, popover.isShown { popover.performClose(nil) }
      result(nil)

    case "timer.changed":
      // The main window started or stopped something; an open popover
      // should show it now rather than at its next poll.
      popoverChannel?.invokeMethod("timer.refresh", arguments: nil)
      result(nil)

    default:
      result(FlutterMethodNotImplemented)
    }
  }

  // MARK: The item

  @objc private func clicked(_ sender: NSStatusBarButton) {
    if NSApp.currentEvent?.type == .rightMouseUp {
      showMenu()
    } else if popover.isShown {
      popover.performClose(sender)
    } else {
      show(mode: "panel")
    }
  }

  private func showMenu() {
    let menu = NSMenu()
    menu.addItem(withTitle: "Open LifePete", action: #selector(openWindow), keyEquivalent: "").target = self
    menu.addItem(withTitle: "Settings…", action: #selector(openSettings), keyEquivalent: "").target = self
    menu.addItem(.separator())
    menu.addItem(withTitle: "Quit LifePete", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    statusItem.menu = menu
    statusItem.button?.performClick(nil)
    statusItem.menu = nil
  }

  @objc private func openWindow() { open(section: nil, route: nil) }
  @objc private func openSettings() { open(section: nil, route: "settings") }

  // MARK: The popover

  private func ensureEngine() {
    guard popoverEngine == nil else { return }
    let engine = FlutterEngine(name: "popover", project: nil, allowHeadlessExecution: true)
    RegisterGeneratedPlugins(registry: engine)
    engine.run(withEntrypoint: "popoverMain")
    let controller = FlutterViewController(engine: engine, nibName: nil, bundle: nil)
    controller.backgroundColor = .clear
    // Flutter's view sits inside a plain container rather than being the
    // popover's content view itself. On macOS 13.3.1 and later the engine
    // leaves mouseDown and mouseUp to NSView's default, which passes them up
    // to the view controller — except, on macOS 26, in a popover's content
    // view, where they stop there and no click reaches Flutter
    // (flutter/flutter#115015 was the same bug on older macOS).
    let container = NSViewController()
    container.view = NSView(frame: NSRect(origin: .zero, size: popover.contentSize))
    container.addChild(controller)
    controller.view.frame = container.view.bounds
    controller.view.autoresizingMask = [.width, .height]
    container.view.addSubview(controller.view)
    popover.contentViewController = container

    let channel = FlutterMethodChannel(name: Self.popoverChannelName, binaryMessenger: engine.binaryMessenger)
    channel.setMethodCallHandler { [weak self] call, result in
      self?.handlePopover(call, result)
    }
    popoverEngine = engine
    popoverChannel = channel
  }

  private func show(mode: String) {
    guard statusItem.isVisible, let button = statusItem.button else { return }
    ensureEngine()
    popoverChannel?.invokeMethod("popover.show", arguments: ["mode": mode])
    NSApp.activate(ignoringOtherApps: true)
    popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
    popover.contentViewController?.view.window?.makeKey()
  }

  func popoverDidClose(_ notification: Notification) {
    popoverChannel?.invokeMethod("popover.hidden", arguments: nil)
  }

  private func handlePopover(_ call: FlutterMethodCall, _ result: @escaping FlutterResult) {
    let args = call.arguments as? [String: Any] ?? [:]
    switch call.method {
    case "popover.close":
      popover.performClose(nil)
      result(nil)

    case "popover.resize":
      if let height = args["height"] as? Double {
        popover.contentSize = NSSize(width: popover.contentSize.width, height: CGFloat(height))
      }
      result(nil)

    case "app.open":
      open(section: args["section"] as? String, route: args["route"] as? String)
      result(nil)

    case "timer.changed":
      mainChannel.invokeMethod("timer.refresh", arguments: nil)
      result(nil)

    default:
      result(FlutterMethodNotImplemented)
    }
  }

  /// Brings the main window forward, on [section] (today, flow, coach,
  /// body) or [route] (settings, focus) when given.
  private func open(section: String?, route: String?) {
    popover.performClose(nil)
    NSApp.activate(ignoringOtherApps: true)
    window?.makeKeyAndOrderFront(nil)
    var args: [String: Any] = [:]
    if let section { args["section"] = section }
    if let route { args["route"] = route }
    mainChannel.invokeMethod("window.show", arguments: args)
  }

  // MARK: The hot key

  private func registerHotKey() {
    var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    let me = Unmanaged.passUnretained(self).toOpaque()
    InstallEventHandler(GetApplicationEventTarget(), { _, _, userData in
      guard let userData else { return noErr }
      let controller = Unmanaged<StatusItemController>.fromOpaque(userData).takeUnretainedValue()
      DispatchQueue.main.async { controller.hotKeyPressed() }
      return noErr
    }, 1, &spec, me, nil)
    let id = EventHotKeyID(signature: OSType(0x4C50_4554), id: 1)  // 'LPET'
    RegisterEventHotKey(
      UInt32(kVK_ANSI_T), UInt32(controlKey | optionKey), id, GetApplicationEventTarget(), 0, &hotKey)
  }

  private func hotKeyPressed() {
    if popover.isShown {
      popover.performClose(nil)
    } else {
      show(mode: "palette")
    }
  }
}
