package collector

import "testing"

func TestCategoryFor_KnownApps(t *testing.T) {
	tests := []struct {
		bundleID string
		want     string
	}{
		{"com.apple.dt.Xcode", "coding"},
		{"com.microsoft.VSCode", "coding"},
		{"com.apple.Terminal", "coding"},
		{"com.googlecode.iterm2", "coding"},
		{"com.tinyspeck.slackmacgap", "communication"},
		{"com.apple.Safari", "browser"},
		{"com.google.Chrome", "browser"},
		{"com.figma.Desktop", "design"},
		{"notion.id", "writing"},
		{"md.obsidian", "writing"},
		{"com.spotify.client", "social"},
	}

	for _, tt := range tests {
		got := CategoryFor(tt.bundleID)
		if got != tt.want {
			t.Errorf("CategoryFor(%q) = %q, want %q", tt.bundleID, got, tt.want)
		}
	}
}

func TestCategoryFor_Unknown(t *testing.T) {
	got := CategoryFor("com.unknown.app")
	if got != "other" {
		t.Errorf("expected 'other' for unknown app, got %q", got)
	}
}

func TestCategoryFor_Empty(t *testing.T) {
	got := CategoryFor("")
	if got != "other" {
		t.Errorf("expected 'other' for empty bundle ID, got %q", got)
	}
}

func TestCategoryFor_WindowsExecutables(t *testing.T) {
	// Keys are the extension-less basenames windowsExeIdentity emits,
	// so these are the literal values the Windows collector produces.
	tests := []struct {
		exe  string
		want string
	}{
		{"Code", "coding"},
		{"devenv", "coding"},
		{"WindowsTerminal", "coding"},
		{"pwsh", "coding"},
		{"idea64", "coding"},
		{"slack", "communication"},
		{"Discord", "communication"},
		{"chrome", "browser"},
		{"msedge", "browser"},
		{"Figma", "design"},
		{"Obsidian", "writing"},
		{"WINWORD", "writing"},
		{"Spotify", "social"},
	}

	for _, tt := range tests {
		if got := CategoryFor(tt.exe); got != tt.want {
			t.Errorf("CategoryFor(%q) = %q, want %q", tt.exe, got, tt.want)
		}
	}
}

// TestCategoryFor_CaseInsensitiveFallback covers the reason the
// fallback exists: the same application is spelled differently by
// platform, and a case miss is indistinguishable from an unknown app
// once it reaches the score.
func TestCategoryFor_CaseInsensitiveFallback(t *testing.T) {
	tests := []struct {
		id   string
		want string
	}{
		{"CHROME", "browser"},
		{"MsEdge", "browser"},
		{"spotify", "social"},
		{"DISCORD", "communication"},
		{"windowsterminal", "coding"},
	}

	for _, tt := range tests {
		if got := CategoryFor(tt.id); got != tt.want {
			t.Errorf("CategoryFor(%q) = %q, want %q", tt.id, got, tt.want)
		}
	}
}

// TestCategoryFor_UnknownStillOther guards against the case-insensitive
// fallback turning into a catch-all that classifies everything.
func TestCategoryFor_UnknownStillOther(t *testing.T) {
	for _, id := range []string{"SomeRandomApp", "totally.unknown.thing", "xyzzy"} {
		if got := CategoryFor(id); got != "other" {
			t.Errorf("CategoryFor(%q) = %q, want \"other\"", id, got)
		}
	}
}
