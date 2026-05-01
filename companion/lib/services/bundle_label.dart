/// Best-effort mapping from common macOS bundle ids → human labels,
/// plus a [shortBundleLabel] helper that falls back to the trailing
/// reverse-DNS segment for unknown ids.
///
/// Cross-language parity: matches the web's bundleLabel.ts. Both
/// the FlowHeadline (web home page) and the FlowScreen (companion)
/// render bundle ids with the same friendly names so users see e.g.
/// "VS Code" rather than "com.microsoft.VSCode" everywhere.
library;

const Map<String, String> _appLabels = {
  'com.microsoft.VSCode': 'VS Code',
  'com.apple.dt.Xcode': 'Xcode',
  'com.jetbrains.intellij': 'IntelliJ',
  'com.jetbrains.WebStorm': 'WebStorm',
  'com.jetbrains.pycharm': 'PyCharm',
  'com.jetbrains.goland': 'GoLand',
  'com.googlecode.iterm2': 'iTerm',
  'com.apple.Terminal': 'Terminal',
  'com.mitchellh.ghostty': 'Ghostty',
  'net.kovidgoyal.kitty': 'Kitty',
  'com.tinyspeck.slackmacgap': 'Slack',
  'com.hnc.Discord': 'Discord',
  'com.tdesktop.Telegram': 'Telegram',
  'com.google.Chrome': 'Chrome',
  'com.apple.Safari': 'Safari',
  'org.mozilla.firefox': 'Firefox',
  'com.brave.Browser': 'Brave',
  'com.figma.Desktop': 'Figma',
  'com.linear.linear': 'Linear',
  'notion.id': 'Notion',
  'md.obsidian': 'Obsidian',
  'com.apple.mail': 'Mail',
  'com.spotify.client': 'Spotify',
  'com.apple.Music': 'Music',
  'com.apple.iCal': 'Calendar',
  'com.twitter.twitter-mac': 'Twitter',
};

/// Returns a human-friendly app name for a macOS bundle id, falling
/// back to the trailing reverse-DNS segment for unknown ids. Empty
/// input returns empty.
String shortBundleLabel(String id) {
  if (id.isEmpty) return '';
  final known = _appLabels[id];
  if (known != null) return known;
  final dot = id.lastIndexOf('.');
  return dot >= 0 ? id.substring(dot + 1) : id;
}
