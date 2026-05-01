package collector

import "testing"

func TestParseLsappinfo(t *testing.T) {
	output := `"bundleID" = "com.apple.dt.Xcode"
"name" = "Xcode"
`
	bundleID, appName := parseLsappinfo(output)
	if bundleID != "com.apple.dt.Xcode" {
		t.Errorf("expected com.apple.dt.Xcode, got %q", bundleID)
	}
	if appName != "Xcode" {
		t.Errorf("expected Xcode, got %q", appName)
	}
}

func TestParseLsappinfo_VSCode(t *testing.T) {
	output := `"bundleID" = "com.microsoft.VSCode"
"name" = "Code"
"pid" = 12345
`
	bundleID, appName := parseLsappinfo(output)
	if bundleID != "com.microsoft.VSCode" {
		t.Errorf("expected com.microsoft.VSCode, got %q", bundleID)
	}
	if appName != "Code" {
		t.Errorf("expected Code, got %q", appName)
	}
}

func TestParseLsappinfo_Empty(t *testing.T) {
	bundleID, appName := parseLsappinfo("")
	if bundleID != "" || appName != "" {
		t.Errorf("expected empty for empty input, got %q %q", bundleID, appName)
	}
}

func TestParseLsappinfo_Malformed(t *testing.T) {
	bundleID, appName := parseLsappinfo("no equals sign here\njust garbage")
	if bundleID != "" || appName != "" {
		t.Errorf("expected empty for malformed, got %q %q", bundleID, appName)
	}
}

func TestParseLsappinfoLine(t *testing.T) {
	key, val, ok := parseLsappinfoLine(`"bundleID" = "com.test.App"`)
	if !ok || key != "bundleID" || val != "com.test.App" {
		t.Errorf("got key=%q val=%q ok=%v", key, val, ok)
	}

	_, _, ok = parseLsappinfoLine("no-equals")
	if ok {
		t.Error("expected ok=false for line without =")
	}
}

// --- parseXpropClass: Linux X11 frontmost-app parsing ---

func TestParseXpropClass_StandardFormat(t *testing.T) {
	// `xprop -id <wid> WM_CLASS` produces:
	//
	//   WM_CLASS(STRING) = "instance", "ClassName"
	//
	// The class (second value) is what we want — that's the
	// app-identifier equivalent we send up as bundleID on Linux.
	got := parseXpropClass(`WM_CLASS(STRING) = "code", "Code"`)
	if got != "Code" {
		t.Errorf("expected Code, got %q", got)
	}
}

func TestParseXpropClass_UpstreamSpaces(t *testing.T) {
	// Real xprop output has variable spacing depending on locale and
	// the X server. The parser strips both quotes and surrounding
	// whitespace so a less-tidy line still resolves cleanly.
	got := parseXpropClass(`WM_CLASS(STRING) =   "firefox" ,  "Firefox"  `)
	if got != "Firefox" {
		t.Errorf("expected Firefox, got %q", got)
	}
}

func TestParseXpropClass_NoEqualsReturnsEmpty(t *testing.T) {
	// Defensive: if xprop returns an unexpected line shape we don't
	// want to send garbage up as the bundle id. Empty is the same
	// "no signal" the daemon already handles gracefully.
	if got := parseXpropClass("WM_CLASS not found"); got != "" {
		t.Errorf("expected empty for missing equals, got %q", got)
	}
}

func TestParseXpropClass_SingleValueFallsBackToWholeRhs(t *testing.T) {
	// Some windows have only one WM_CLASS entry (no comma). We fall
	// back to whatever's after the equals so we still return SOMETHING
	// rather than dropping the signal entirely.
	got := parseXpropClass(`WM_CLASS(STRING) = "Solo"`)
	if got != "Solo" {
		t.Errorf("expected Solo, got %q", got)
	}
}

// --- parseSwaymsgTree: Wayland / Sway frontmost-app parsing ---

func TestParseSwaymsgTree_FindsFocusedAppId(t *testing.T) {
	// swaymsg -t get_tree returns a JSON tree. The focused window
	// has `"focused": true` near `"app_id": "..."`. We don't full-
	// JSON-parse the output (the daemon is hot-path and the tree
	// can be large) — line-window match is sufficient.
	tree := `{
  "nodes": [
    {
      "type": "con",
      "name": "main",
      "app_id": "firefox",
      "focused": true
    }
  ]
}`
	app, name := parseSwaymsgTree(tree)
	if app != "firefox" || name != "firefox" {
		t.Errorf("expected firefox/firefox, got %q/%q", app, name)
	}
}

func TestParseSwaymsgTree_AppIdAboveFocused(t *testing.T) {
	// app_id sits ABOVE focused in the JSON. The 10-line lookback
	// window covers this; locked in here so a future tightening of
	// the window doesn't silently drop the case.
	tree := `{
  "app_id": "code",
  "type": "con",
  "name": "main",
  "focused": true
}`
	app, _ := parseSwaymsgTree(tree)
	if app != "code" {
		t.Errorf("expected code, got %q", app)
	}
}

func TestParseSwaymsgTree_NullAppIdReturnsEmpty(t *testing.T) {
	// XWayland windows (X11 apps under Sway) report `app_id: null`.
	// We return empty so the daemon falls through gracefully — the
	// X11 path of frontmostAppLinux would then re-fetch via xprop.
	tree := `{
  "type": "con",
  "app_id": null,
  "focused": true
}`
	app, _ := parseSwaymsgTree(tree)
	if app != "" {
		t.Errorf("expected empty for null app_id, got %q", app)
	}
}

func TestParseSwaymsgTree_NoFocusedReturnsEmpty(t *testing.T) {
	// All-unfocused tree — happens transiently when the user clicks
	// the desktop. Nothing to surface; the next sample picks up the
	// new focused window.
	tree := `{
  "type": "root",
  "app_id": "firefox",
  "focused": false
}`
	app, _ := parseSwaymsgTree(tree)
	if app != "" {
		t.Errorf("expected empty when no window is focused, got %q", app)
	}
}

func TestParseSwaymsgTree_MultipleWindowsPicksFocused(t *testing.T) {
	// A real desktop has multiple windows. swaymsg pretty-prints
	// with each JSON field on its own line, so the line-scan parser
	// has 10 lines of lookback to find the matching app_id. The
	// foreground window's app_id should win even though a background
	// app_id appears earlier in the tree.
	tree := `{
  "nodes": [
    {
      "app_id": "background_app",
      "focused": false
    },
    {
      "app_id": "foreground_app",
      "focused": true
    }
  ]
}`
	app, _ := parseSwaymsgTree(tree)
	if app != "foreground_app" {
		t.Errorf("expected foreground_app, got %q", app)
	}
}
