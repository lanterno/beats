# Homebrew Tap — `homebrew-beats`

> **Status: ready to publish.** The release workflow at
> `.github/workflows/release-daemon.yml` builds and uploads
> darwin/linux × arm64/amd64 tarballs on every `v*` tag. The canonical
> formula lives at `integrations/homebrew-formula/beatsd.rb`. The only
> step left is creating the public `homebrew-beats` tap repo and
> mirroring the formula there — see
> `integrations/homebrew-formula/README.md` for the one-time wiring.

Distributes the `beatsd` daemon binary via `brew install <user>/beats/beatsd`.

## Why

Users shouldn't need Go installed to run the daemon. A Homebrew tap provides a single-command install on macOS (and Linux via Linuxbrew), with automatic updates via `brew upgrade`.

## Repository Structure

```
homebrew-beats/          (separate repo: github.com/ahmedElghable/homebrew-beats)
├── Formula/
│   └── beatsd.rb        Homebrew formula
└── README.md
```

## Formula

```ruby
class Beatsd < Formula
  desc "Ambient flow tracking daemon for Beats"
  homepage "https://github.com/ahmedElghable/beats"
  version "0.1.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/ahmedElghable/beats/releases/download/v#{version}/beatsd-darwin-arm64.tar.gz"
      sha256 "PLACEHOLDER"
    end
    on_intel do
      url "https://github.com/ahmedElghable/beats/releases/download/v#{version}/beatsd-darwin-amd64.tar.gz"
      sha256 "PLACEHOLDER"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/ahmedElghable/beats/releases/download/v#{version}/beatsd-linux-arm64.tar.gz"
      sha256 "PLACEHOLDER"
    end
    on_intel do
      url "https://github.com/ahmedElghable/beats/releases/download/v#{version}/beatsd-linux-amd64.tar.gz"
      sha256 "PLACEHOLDER"
    end
  end

  def install
    bin.install "beatsd"
  end

  service do
    run [opt_bin/"beatsd", "run"]
    keep_alive true
    log_path var/"log/beatsd.log"
    error_log_path var/"log/beatsd.log"
  end

  test do
    assert_match "beatsd", shell_output("#{bin}/beatsd version")
  end
end
```

## Build & Release Pipeline

### 1. Cross-compile binaries

Add to the Beats repo's CI (GitHub Actions):

```yaml
# .github/workflows/release-daemon.yml
name: Release Daemon
on:
  push:
    tags: ["v*"]

jobs:
  build:
    strategy:
      matrix:
        include:
          - goos: darwin
            goarch: arm64
          - goos: darwin
            goarch: amd64
          - goos: linux
            goarch: arm64
          - goos: linux
            goarch: amd64
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.23"
      - name: Build
        env:
          GOOS: ${{ matrix.goos }}
          GOARCH: ${{ matrix.goarch }}
        run: |
          cd daemon
          go build -ldflags "-X main.version=${{ github.ref_name }}" \
            -o beatsd ./cmd/beatsd/
          tar czf beatsd-${{ matrix.goos }}-${{ matrix.goarch }}.tar.gz beatsd
      - uses: softprops/action-gh-release@v2
        with:
          files: daemon/beatsd-*.tar.gz
```

### 2. macOS notarization (for Gatekeeper)

For macOS distribution without "unidentified developer" warnings:

1. Sign the binary with an Apple Developer ID: `codesign --sign "Developer ID Application: ..." beatsd`
2. Notarize via `xcrun notarytool submit beatsd.zip --apple-id ... --password ... --team-id ...`
3. Staple the notarization ticket: `xcrun stapler staple beatsd`

This requires an Apple Developer account ($99/year). Skip for initial release — users can allow it via System Settings > Privacy & Security.

### 3. Update the tap formula

After the release workflow creates the GitHub release with tarballs:

```bash
# In the homebrew-beats repo
brew bump-formula-pr --url "https://github.com/.../releases/download/v0.1.0/beatsd-darwin-arm64.tar.gz" \
  --sha256 $(shasum -a 256 beatsd-darwin-arm64.tar.gz | cut -d' ' -f1) \
  Formula/beatsd.rb
```

Or automate via a second GitHub Action that updates the formula on each release.

## Implementation Steps

1. **Create the `homebrew-beats` repo** on GitHub.
2. **Write the formula** (`Formula/beatsd.rb`) with placeholder SHA256s.
3. **Add the release workflow** to the Beats repo (`.github/workflows/release-daemon.yml`).
4. **Tag `v0.1.0`** — workflow builds binaries, creates GitHub release.
5. **Update formula SHA256s** from the release artifacts.
6. **Test**: `brew tap ahmed/beats && brew install beatsd && beatsd version`.
7. **Add `brew services`**: `brew services start beatsd` runs the daemon as a LaunchAgent.

## User Install Flow

```bash
brew tap ahmed/beats
brew install beatsd

# Pair with your Beats account
beatsd pair ABC123

# Start the daemon (runs on login)
brew services start beatsd

# Or run manually
beatsd run

# Try dry-run first (recommended for new users)
beatsd --dry-run run
```

## Notes

- The `service` block in the formula creates a macOS LaunchAgent (`~/Library/LaunchAgents/homebrew.mxcl.beatsd.plist`) or a Linux systemd user unit.
- The formula installs the binary to `/opt/homebrew/bin/beatsd` (Apple Silicon) or `/usr/local/bin/beatsd` (Intel).
- Version updates: `brew upgrade beatsd` pulls the latest formula and binary.
- No cask needed — `beatsd` is a CLI tool, not a `.app` bundle.
