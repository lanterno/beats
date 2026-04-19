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
