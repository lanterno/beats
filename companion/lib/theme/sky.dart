import 'package:material_ui/material_ui.dart';
import 'package:google_fonts/google_fonts.dart';

/// The two hours the app is drawn in, the same two the web app offers:
/// `afternoon` (light) and `dusk` (dark). Values are the web's tokens in
/// `ui/client/global.css`, converted from HSL, so the Mac app and lifepete.com
/// read as one product. Change a colour there and here together.
class SkyPalette extends ThemeExtension<SkyPalette> {
  /// Text and icons on a panel.
  final Color ink;

  /// Secondary text: captions, units, the quiet half of a label.
  final Color inkMuted;

  /// Secondary text that sits on the sky rather than on a panel, where
  /// [inkMuted] would be too faint.
  final Color inkOnSky;

  /// Cloud-white panels and the sidebar behind them.
  final Color panel;
  final Color sidebar;

  /// Sunlight: the running timer, today, the one primary action.
  final Color sun;

  /// The sun as text on a panel, where [sun] itself is not legible.
  final Color sunInk;

  /// The sky-blue tint behind chips, tiles, secondary buttons and hover.
  final Color wash;

  /// The heavier wash: the selected sidebar row, an active tab.
  final Color washStrong;

  /// The track behind a fill (rings, progress bars, empty days).
  final Color track;

  /// Hairline dividers.
  final Color hairline;

  /// Leaf green for hours ahead and good news; [leafInk] is its text tone.
  final Color leaf;
  final Color leafInk;

  /// Persimmon for hours owed and destructive actions; [persimmonInk] is
  /// its text tone.
  final Color persimmon;
  final Color persimmonInk;

  /// The sky behind every screen, top to bottom, and the hills at its foot.
  final List<Color> sky;
  final List<Color> hills;

  const SkyPalette({
    required this.ink,
    required this.inkMuted,
    required this.inkOnSky,
    required this.panel,
    required this.sidebar,
    required this.sun,
    required this.sunInk,
    required this.wash,
    required this.washStrong,
    required this.track,
    required this.hairline,
    required this.leaf,
    required this.leafInk,
    required this.persimmon,
    required this.persimmonInk,
    required this.sky,
    required this.hills,
  });

  static const afternoon = SkyPalette(
    ink: Color(0xFF2B3A44),
    inkMuted: Color(0xFF5C6770),
    inkOnSky: Color(0xFF3D5160),
    panel: Color(0xF2FFFDF7),
    sidebar: Color(0xB8FFFDF7),
    sun: Color(0xFFF2B233),
    sunInk: Color(0xFF8C5E12),
    wash: Color(0x2972B0D6),
    washStrong: Color(0x4772B0D6),
    track: Color(0xFFD3E2EA),
    hairline: Color(0x172B3A44),
    leaf: Color(0xFF3E8D53),
    leafInk: Color(0xFF2A6F3D),
    persimmon: Color(0xFFD2683F),
    persimmonInk: Color(0xFFA84924),
    sky: [Color(0xFF8CC1E2), Color(0xFFBCDDEE), Color(0xFFE4F0F1), Color(0xFFE9F2E6)],
    hills: [Color(0xFFB9D9A8), Color(0xFF8AC07C), Color(0xFF5C9F5E)],
  );

  static const dusk = SkyPalette(
    ink: Color(0xFFEEF2F7),
    inkMuted: Color(0xFFA9B4C2),
    inkOnSky: Color(0xFFC9D3E0),
    panel: Color(0xF0232F48),
    sidebar: Color(0xDB232F48),
    sun: Color(0xFFF5C45A),
    sunInk: Color(0xFFF5C45A),
    wash: Color(0x248DBDE6),
    washStrong: Color(0x478DBDE6),
    track: Color(0xFF3A4255),
    hairline: Color(0x1AEEF2F7),
    leaf: Color(0xFF8DD5A0),
    leafInk: Color(0xFF8DD5A0),
    persimmon: Color(0xFFF2A07E),
    persimmonInk: Color(0xFFF2A07E),
    sky: [Color(0xFF1A2446), Color(0xFF2E3E6E), Color(0xFF6A5A82), Color(0xFFC98A63)],
    hills: [Color(0xFF3B5470), Color(0xFF2C4A44), Color(0xFF1F3A31)],
  );

  /// Text on a [sun] fill. The sun is light in both hours, so this is the
  /// afternoon ink in both.
  Color get onSun => const Color(0xFF2B3A44);

  @override
  SkyPalette copyWith() => this;

  @override
  SkyPalette lerp(SkyPalette? other, double t) {
    if (other == null) return this;
    Color c(Color a, Color b) => Color.lerp(a, b, t)!;
    List<Color> l(List<Color> a, List<Color> b) =>
        [for (var i = 0; i < a.length; i++) c(a[i], b[i])];
    return SkyPalette(
      ink: c(ink, other.ink),
      inkMuted: c(inkMuted, other.inkMuted),
      inkOnSky: c(inkOnSky, other.inkOnSky),
      panel: c(panel, other.panel),
      sidebar: c(sidebar, other.sidebar),
      sun: c(sun, other.sun),
      sunInk: c(sunInk, other.sunInk),
      wash: c(wash, other.wash),
      washStrong: c(washStrong, other.washStrong),
      track: c(track, other.track),
      hairline: c(hairline, other.hairline),
      leaf: c(leaf, other.leaf),
      leafInk: c(leafInk, other.leafInk),
      persimmon: c(persimmon, other.persimmon),
      persimmonInk: c(persimmonInk, other.persimmonInk),
      sky: l(sky, other.sky),
      hills: l(hills, other.hills),
    );
  }
}

extension SkyContext on BuildContext {
  SkyPalette get sky => Theme.of(this).extension<SkyPalette>()!;
}

/// The two rounded faces the web app uses: M PLUS Rounded 1c for display
/// figures and every column of digits, Zen Maru Gothic for everything read.
/// Styles carry no colour, so text takes the ink of the hour it is drawn in.
class SkyType {
  static TextStyle display(double size, {FontWeight weight = FontWeight.w800}) =>
      GoogleFonts.mPlusRounded1c(fontSize: size, fontWeight: weight, height: 1.15);

  /// Digits that tick or line up: timers, totals, scores.
  static TextStyle figure(double size, {FontWeight weight = FontWeight.w800}) =>
      GoogleFonts.mPlusRounded1c(
        fontSize: size,
        fontWeight: weight,
        height: 1.0,
        fontFeatures: const [FontFeature.tabularFigures()],
      );

  static TextStyle body(double size, {FontWeight weight = FontWeight.w400, double height = 1.5}) =>
      GoogleFonts.zenMaruGothic(fontSize: size, fontWeight: weight, height: height);
}

ThemeData buildSkyTheme(SkyPalette p, Brightness brightness) {
  final base = ThemeData(brightness: brightness, useMaterial3: true);
  final textTheme = GoogleFonts.zenMaruGothicTextTheme(base.textTheme).apply(
    bodyColor: p.ink,
    displayColor: p.ink,
  );
  return base.copyWith(
    extensions: [p],
    scaffoldBackgroundColor: Colors.transparent,
    canvasColor: p.panel,
    dividerColor: p.hairline,
    textTheme: textTheme,
    iconTheme: IconThemeData(color: p.ink, size: 20),
    colorScheme: ColorScheme.fromSeed(
      seedColor: p.sun,
      brightness: brightness,
    ).copyWith(
      primary: p.sun,
      onPrimary: p.onSun,
      secondary: p.wash,
      onSecondary: p.ink,
      surface: p.panel.withValues(alpha: 1),
      onSurface: p.ink,
      error: p.persimmon,
      onError: p.onSun,
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: p.sunInk,
      selectionColor: p.sun.withValues(alpha: 0.35),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: p.ink,
      contentTextStyle: SkyType.body(14).copyWith(color: p.panel.withValues(alpha: 1)),
      actionTextColor: p.sun,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: p.panel.withValues(alpha: 1),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: p.ink, borderRadius: BorderRadius.circular(10)),
      textStyle: SkyType.body(12).copyWith(color: p.panel.withValues(alpha: 1)),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? p.leaf : p.track,
      ),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.sun, linearTrackColor: p.track),
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: p.wash,
      hintStyle: SkyType.body(15).copyWith(color: p.inkMuted),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(999),
        borderSide: BorderSide.none,
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(999),
        borderSide: BorderSide(color: p.sun, width: 2),
      ),
    ),
    datePickerTheme: DatePickerThemeData(
      backgroundColor: p.panel.withValues(alpha: 1),
      surfaceTintColor: Colors.transparent,
    ),
    timePickerTheme: TimePickerThemeData(backgroundColor: p.panel.withValues(alpha: 1)),
  );
}
