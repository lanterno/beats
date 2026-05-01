package main

import (
	"encoding/json"
	"fmt"
	"runtime"
	"runtime/debug"
	"strings"
)

// versionInfo bundles every fact about this binary that's useful in a bug
// report. version (the upstream tag like "v0.1.0", or "dev" for unreleased
// builds) is set via -ldflags at release time; everything else is read
// from the runtime + build-info embedded by the Go toolchain.
//
// JSON tags are stable — `beatsd version --json` is part of the public
// contract once shipped, used for CI and the companion's about screen.
type versionInfo struct {
	Version   string `json:"version"`    // e.g. "v0.1.0" or "dev"
	GitSHA    string `json:"git_sha"`    // 12-char prefix of the embedded vcs.revision
	GitDirty  bool   `json:"git_dirty"`  // true if vcs.modified=true at build time
	BuildDate string `json:"build_date"` // build timestamp from vcs.time, ISO 8601
	GoVersion string `json:"go_version"` // e.g. "go1.23.0"
	OSArch    string `json:"os_arch"`    // "darwin/arm64", "linux/amd64", …
	CgoBuild  bool   `json:"cgo_build"`  // whether cgo was on at build time (matters for cadence)
}

func collectVersionInfo() versionInfo {
	v := versionInfo{
		Version:   version,
		GoVersion: runtime.Version(),
		OSArch:    fmt.Sprintf("%s/%s", runtime.GOOS, runtime.GOARCH),
	}

	// debug.ReadBuildInfo gives us VCS settings the Go toolchain stamped
	// into the binary at build time. Only present for binaries built with
	// `go build` from inside a VCS-tracked tree — `go run` won't populate.
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, s := range info.Settings {
			switch s.Key {
			case "vcs.revision":
				if len(s.Value) > 12 {
					v.GitSHA = s.Value[:12]
				} else {
					v.GitSHA = s.Value
				}
			case "vcs.modified":
				v.GitDirty = s.Value == "true"
			case "vcs.time":
				v.BuildDate = s.Value
			case "CGO_ENABLED":
				v.CgoBuild = s.Value == "1"
			}
		}
	}
	return v
}

// formatVersionJSON renders the version info as a single JSON
// object with a trailing newline so a shell prompt lands cleanly
// after `beatsd version --json`. Designed for CI release pipelines
// (`beatsd version --json | jq -r .git_sha`) and the companion's
// nascent about-screen, which would otherwise have to regex-parse
// the human form.
func formatVersionJSON(v versionInfo) (string, error) {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return "", fmt.Errorf("encode JSON: %w", err)
	}
	return string(b) + "\n", nil
}

// String renders the version info as a multi-line block suitable for
// `beatsd version` output. Lined up with two-space indent so it visually
// matches `beatsd doctor` and `beatsd status` output styles.
func (v versionInfo) String() string {
	var b strings.Builder
	fmt.Fprintf(&b, "  beatsd %s", v.Version)
	if v.GitSHA != "" {
		fmt.Fprintf(&b, " (%s", v.GitSHA)
		if v.GitDirty {
			b.WriteString("-dirty")
		}
		b.WriteString(")")
	}
	b.WriteString("\n")
	if v.BuildDate != "" {
		fmt.Fprintf(&b, "  built:    %s\n", v.BuildDate)
	}
	fmt.Fprintf(&b, "  go:       %s\n", v.GoVersion)
	fmt.Fprintf(&b, "  os/arch:  %s\n", v.OSArch)
	if v.CgoBuild {
		b.WriteString("  cgo:      enabled (cadence path linked)\n")
	} else {
		b.WriteString("  cgo:      disabled (cadence will fall back to 0.5)\n")
	}
	return b.String()
}
