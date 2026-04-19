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
