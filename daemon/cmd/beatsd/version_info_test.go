package main

import (
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
