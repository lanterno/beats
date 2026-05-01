package bundle

import "testing"

// Cross-language parity check: each assertion mirrors a case in
// ui/client/shared/lib/bundleLabel.test.ts and
// companion/test/bundle_label_test.dart. A user looking at the web
// FlowHeadline, the companion FlowScreen, and `beatsd stats` should
// see the same friendly app names everywhere — these tests guard
// against the three implementations drifting.

func TestShortLabel_KnownApps(t *testing.T) {
	for _, c := range []struct {
		id   string
		want string
	}{
		{"com.microsoft.VSCode", "VS Code"},
		{"com.apple.dt.Xcode", "Xcode"},
		{"com.jetbrains.goland", "GoLand"},
	} {
		if got := ShortLabel(c.id); got != c.want {
			t.Errorf("ShortLabel(%q) = %q, want %q", c.id, got, c.want)
		}
	}
}

func TestShortLabel_FallsBackToTrailingSegment(t *testing.T) {
	if got := ShortLabel("com.todesktop.230313mzl4w4u92"); got != "230313mzl4w4u92" {
		t.Errorf("expected trailing segment fallback, got %q", got)
	}
	if got := ShortLabel("com.example.MyApp"); got != "MyApp" {
		t.Errorf("expected MyApp, got %q", got)
	}
}

func TestShortLabel_NoDotReturnsInput(t *testing.T) {
	if got := ShortLabel("standalone"); got != "standalone" {
		t.Errorf("expected unchanged input, got %q", got)
	}
}

func TestShortLabel_EmptyReturnsEmpty(t *testing.T) {
	// Defensive — callers passing an optional top_bundle.key field
	// might land here with "" if the field was omitted. Don't crash,
	// don't return "."
	if got := ShortLabel(""); got != "" {
		t.Errorf("expected empty string, got %q", got)
	}
}
