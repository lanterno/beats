package main

import (
	"encoding/json"
	"strings"
	"testing"
)

// renderString and the field-pulling logic of collectVersionInfo() each have
// their own surface area; we test the rendering directly with a hand-built
// versionInfo struct so we don't depend on debug.ReadBuildInfo (which only
// returns useful data for `go build`-d binaries, not `go run`).

func TestVersionInfo_RendersAllPresentFields(t *testing.T) {
	v := versionInfo{
		Version:   "v0.1.0",
		GitSHA:    "abc123def456",
		GitDirty:  false,
		BuildDate: "2026-04-30T10:00:00Z",
		GoVersion: "go1.23.0",
		OSArch:    "darwin/arm64",
		CgoBuild:  true,
	}
	out := v.String()
	for _, want := range []string{
		"beatsd v0.1.0",
		"abc123def456",
		"built:    2026-04-30T10:00:00Z",
		"go:       go1.23.0",
		"os/arch:  darwin/arm64",
		"cgo:      enabled",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("expected output to contain %q, got:\n%s", want, out)
		}
	}
	if strings.Contains(out, "-dirty") {
		t.Errorf("did not expect -dirty marker; got:\n%s", out)
	}
}

func TestVersionInfo_AppendsDirtyMarker(t *testing.T) {
	v := versionInfo{
		Version:   "dev",
		GitSHA:    "abc123",
		GitDirty:  true,
		GoVersion: "go1.23.0",
		OSArch:    "linux/amd64",
		CgoBuild:  false,
	}
	out := v.String()
	if !strings.Contains(out, "abc123-dirty") {
		t.Errorf("expected -dirty marker on the SHA line; got:\n%s", out)
	}
	if !strings.Contains(out, "cgo:      disabled") {
		t.Errorf("expected cgo: disabled when CgoBuild=false; got:\n%s", out)
	}
}

func TestVersionInfo_OmitsBuildDateAndShaWhenAbsent(t *testing.T) {
	// `go run` builds don't get a vcs.revision or vcs.time stamped in.
	// The renderer should still produce something useful — version line
	// without a SHA, no built: line at all.
	v := versionInfo{
		Version:   "dev",
		GoVersion: "go1.23.0",
		OSArch:    "darwin/arm64",
	}
	out := v.String()
	if !strings.HasPrefix(out, "  beatsd dev\n") {
		t.Errorf("expected version line with no SHA decoration; got:\n%s", out)
	}
	if strings.Contains(out, "built:") {
		t.Errorf("did not expect built: line when BuildDate is empty; got:\n%s", out)
	}
}

// --- formatVersionJSON ---

// JSON output is what CI release pipelines and the companion's
// nascent about screen will consume. The shape is the public
// --json contract — tag renames here are breaking.

func TestFormatVersionJSON_RoundTrips(t *testing.T) {
	v := versionInfo{
		Version:   "v0.1.0",
		GitSHA:    "abc123def456",
		GitDirty:  true,
		BuildDate: "2026-04-30T10:00:00Z",
		GoVersion: "go1.23.0",
		OSArch:    "darwin/arm64",
		CgoBuild:  true,
	}
	out, err := formatVersionJSON(v)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasSuffix(out, "\n") {
		t.Errorf("expected trailing newline so shell prompt lands cleanly, got %q", out)
	}
	var decoded versionInfo
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("output should round-trip through json.Unmarshal: %v\noutput: %s", err, out)
	}
	if decoded != v {
		t.Errorf("round-trip mismatch:\n want %+v\n got  %+v", v, decoded)
	}
}

func TestFormatVersionJSON_StableKeyNames(t *testing.T) {
	// Locks the wire keys — CI pipelines that grep for
	// `.git_sha` would break silently if a future refactor
	// renamed the JSON tags.
	out, err := formatVersionJSON(versionInfo{
		Version:   "v0.1.0",
		GitSHA:    "abc123",
		GoVersion: "go1.23.0",
		OSArch:    "darwin/arm64",
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		`"version"`, `"git_sha"`, `"git_dirty"`,
		`"build_date"`, `"go_version"`, `"os_arch"`, `"cgo_build"`,
	} {
		if !strings.Contains(out, want) {
			t.Errorf("expected stable key %s in JSON, got: %s", want, out)
		}
	}
}

func TestFormatVersionJSON_GoRunStyleIsValid(t *testing.T) {
	// `go run` builds produce a versionInfo with empty git_sha /
	// build_date / cgo_build=false. The JSON form should still be
	// valid + decodable rather than producing partial output.
	out, err := formatVersionJSON(versionInfo{
		Version:   "dev",
		GoVersion: "go1.23.0",
		OSArch:    "darwin/arm64",
	})
	if err != nil {
		t.Fatal(err)
	}
	var decoded versionInfo
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("expected valid JSON for go-run-style versionInfo, got: %v", err)
	}
	if decoded.Version != "dev" || decoded.GitSHA != "" {
		t.Errorf("decode wrong: %+v", decoded)
	}
}
