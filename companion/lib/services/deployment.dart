/// The LifePete server a build pairs with when nobody names another, chosen
/// when it is built — never guessed:
///
///   flutter build appbundle --dart-define-from-file=config/lifepete.json
///   flutter run -d macos   --dart-define-from-file=config/local.json
///
/// A build given neither (the tests, a bare `flutter run`) has no server of
/// its own: pairing asks for one instead of quietly pointing at localhost.
library;

/// The API's base URL, e.g. https://api.lifepete.com; empty when unset.
const builtInApiUrl = String.fromEnvironment('LIFEPETE_API_URL');

/// The web app's base URL, e.g. https://lifepete.com; empty when unset.
const builtInWebUrl = String.fromEnvironment('LIFEPETE_WEB_URL');
