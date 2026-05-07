import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  /// Held strong so its method-channel handler stays alive for the
  /// lifetime of the window. The bridge is initialized once awakeFromNib
  /// runs and torn down implicitly when the window deinits.
  private var peteMacOS: PeteMacOS?

  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)

    RegisterGeneratedPlugins(registry: flutterViewController)

    let registrar = flutterViewController.registrar(forPlugin: "PeteMacOS")
    peteMacOS = PeteMacOS(registrar: registrar)

    super.awakeFromNib()
  }
}
