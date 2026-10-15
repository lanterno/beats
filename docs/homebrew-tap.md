# Homebrew Tap — `homebrew-beats`

> **Status: ready to publish.** The release workflow at
> `.github/workflows/release-daemon.yml` builds and uploads
> darwin/linux × arm64/amd64 tarballs on every `v*` tag. The canonical
> formula lives at `integrations/homebrew-formula/beatsd.rb`. The only
> step left is creating the public `homebrew-beats` tap repo and
> mirroring the formula there — see
> `integrations/homebrew-formula/README.md` for the one-time wiring.

Distributes the `beatsd` daemon binary via `brew install <user>/beats/beatsd`,
so users don't need Go installed and `brew upgrade` keeps them current.

## Outstanding work

Tracked in Linear — the [LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de), milestone
*Homebrew tap*: the tap repo and the first release with its smoke test
(AHM-12), bumping the formula on each release (AHM-13), and notarization
(AHM-14). `v0.1.0` and `v0.1.1` are already taken by tags from 2015 with
no assets, so the first real release needs a new number.

## User install flow (post-publish)

```bash
brew tap <user>/beats
brew install beatsd

beatsd pair ABC123        # exchange a 6-char code from web Settings
brew services start beatsd  # LaunchAgent / systemd user unit

# Or run manually / try dry-run first
beatsd run
beatsd --dry-run run
```

## Notes

- The `service` block in the formula creates a macOS LaunchAgent
  (`~/Library/LaunchAgents/homebrew.mxcl.beatsd.plist`) or a Linux
  systemd user unit.
- The formula installs the binary to `/opt/homebrew/bin/beatsd`
  (Apple Silicon) or `/usr/local/bin/beatsd` (Intel).
- Version updates: `brew upgrade beatsd` pulls the latest formula and
  binary.
- No cask needed — `beatsd` is a CLI tool, not a `.app` bundle.
