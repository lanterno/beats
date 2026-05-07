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

### `[external-resource]` Tap repo bootstrap + first release

1. **Create the tap repo** on GitHub: `<your-user>/homebrew-beats`.
   Add `Formula/beatsd.rb` containing exactly the contents of
   `integrations/homebrew-formula/beatsd.rb` (the `Formula/` path is
   what `brew tap` looks for).
2. **Cut the first release** — `git tag v0.1.0 && git push --tags`.
   `release-daemon.yml` produces the four tarballs on the GitHub
   Release.
3. **Fill in SHA256s** in the tap's `Formula/beatsd.rb` (replaces the
   `PLACEHOLDER_*` lines). Either by hand or:

   ```bash
   brew bump-formula-pr \
     --url "https://github.com/<user>/beats/releases/download/v0.1.0/beatsd-darwin-arm64.tar.gz" \
     --sha256 "$(shasum -a 256 beatsd-darwin-arm64.tar.gz | cut -d' ' -f1)" \
     Formula/beatsd.rb
   ```

   A small follow-up workflow could automate this on each release;
   today it's a copy-paste.
4. **Smoke-test**:
   ```bash
   brew tap <user>/beats
   brew install beatsd
   beatsd version
   brew services start beatsd
   ```

Why blocked: needs a GitHub account with permission to create the
public `homebrew-beats` repo, plus a tag-pushed release on this repo.

### `[needs-paid-credentials]` macOS notarization (optional)

Sign + notarize + staple the binary so Gatekeeper doesn't show
"unidentified developer". Requires an Apple Developer account
($99/year). Skip for the initial release — users can allow the binary
via System Settings → Privacy & Security. When ready:

- `codesign --sign "Developer ID Application: ..." beatsd`
- `xcrun notarytool submit beatsd.zip --apple-id ... --password ... --team-id ...`
- `xcrun stapler staple beatsd`

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
