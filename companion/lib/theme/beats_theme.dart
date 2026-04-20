import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Beats ember color palette — warm, hand-crafted, no cold grays.
class BeatsColors {
  // Surfaces
  static const background = Color(0xFF0E0C0A);
  static const surface = Color(0xFF171412);
  static const surfaceAlt = Color(0xFF1E1A15);
  static const border = Color(0xFF2A2520);
  static const borderAccent = Color(0xFF3D3428);

  // Foreground
  static const textPrimary = Color(0xFFF0E8DC);
  static const textSecondary = Color(0xFF9C8E7C);
  static const textTertiary = Color(0xFF5C5247);

  // Accents
  static const amber = Color(0xFFD4952A);
  static const amberMuted = Color(0xFF8B6A2F);
  static const red = Color(0xFFBF4040);
  static const green = Color(0xFF66B366);

  // Transparent variants
  static Color amberGlow = amber.withValues(alpha: 0.15);
  static Color amberSubtle = amber.withValues(alpha: 0.08);
}

/// Centralized text styles with curated font pairings.
class BeatsType {
  // Display — editorial warmth
  static TextStyle displayLarge = GoogleFonts.dmSerifDisplay(
    fontSize: 28,
    fontWeight: FontWeight.w400,
    color: BeatsColors.textPrimary,
    height: 1.2,
  );

  static TextStyle displayMedium = GoogleFonts.dmSerifDisplay(
    fontSize: 22,
    fontWeight: FontWeight.w400,
    color: BeatsColors.textPrimary,
    height: 1.3,
  );

  // Body — clean humanist
  static TextStyle bodyLarge = GoogleFonts.dmSans(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    color: BeatsColors.textPrimary,
    height: 1.6,
  );

  static TextStyle bodyMedium = GoogleFonts.dmSans(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    color: BeatsColors.textPrimary,
    height: 1.5,
  );

  static TextStyle bodySmall = GoogleFonts.dmSans(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    color: BeatsColors.textSecondary,
    height: 1.4,
  );

  // Labels — uppercase tracking
  static TextStyle label = GoogleFonts.dmSans(
    fontSize: 10,
    fontWeight: FontWeight.w600,
    color: BeatsColors.textTertiary,
    letterSpacing: 1.5,
  );

  // Mono — timer digits, numbers
  static TextStyle mono = GoogleFonts.jetBrainsMono(
    fontSize: 40,
    fontWeight: FontWeight.w500,
    color: BeatsColors.textPrimary,
    letterSpacing: 1,
  );

  static TextStyle monoSmall = GoogleFonts.jetBrainsMono(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    color: BeatsColors.textPrimary,
  );

  // Buttons
  static TextStyle button = GoogleFonts.dmSans(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: BeatsColors.textPrimary,
  );

  // Title — medium weight for section headers
  static TextStyle titleMedium = GoogleFonts.dmSans(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    color: BeatsColors.textPrimary,
  );

  static TextStyle titleSmall = GoogleFonts.dmSans(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: BeatsColors.textPrimary,
  );
}

/// Build the full app ThemeData using the Beats palette.
ThemeData buildBeatsTheme() {
  return ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: BeatsColors.background,
    canvasColor: BeatsColors.surface,
    cardColor: BeatsColors.surface,
    dividerColor: BeatsColors.border,
    colorScheme: const ColorScheme.dark(
      primary: BeatsColors.amber,
      secondary: BeatsColors.amber,
      error: BeatsColors.red,
      surface: BeatsColors.surface,
      onPrimary: Color(0xFF1A1408),
      onSecondary: Color(0xFF1A1408),
      onSurface: BeatsColors.textPrimary,
      onError: BeatsColors.textPrimary,
    ),
    textTheme: TextTheme(
      displayLarge: BeatsType.displayLarge,
      displayMedium: BeatsType.displayMedium,
      bodyLarge: BeatsType.bodyLarge,
      bodyMedium: BeatsType.bodyMedium,
      bodySmall: BeatsType.bodySmall,
      labelSmall: BeatsType.label,
      titleMedium: BeatsType.titleMedium,
      titleSmall: BeatsType.titleSmall,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: BeatsColors.surfaceAlt,
      contentTextStyle: BeatsType.bodyMedium,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
    datePickerTheme: DatePickerThemeData(
      backgroundColor: BeatsColors.surface,
      surfaceTintColor: Colors.transparent,
      headerBackgroundColor: BeatsColors.surfaceAlt,
      headerForegroundColor: BeatsColors.textPrimary,
    ),
    timePickerTheme: TimePickerThemeData(
      backgroundColor: BeatsColors.surface,
    ),
    useMaterial3: true,
  );
}
