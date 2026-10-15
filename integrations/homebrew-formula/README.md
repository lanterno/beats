# Homebrew formula

Canonical home for the `beatsd` Homebrew formula, so users can
`brew install lanterno/beats/beatsd` without Go and `brew upgrade` keeps
them current. The file `beatsd.rb` here is what gets copied into the
`homebrew-beats` tap repo, which does not exist yet — creating it and
cutting the first release is AHM-12 in
[Linear](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de)
(milestone *Homebrew tap*).

## Why a copy here

Keeping the formula in this repo means:

- The release workflow + the formula it points at sit next to each
  other and version together.
- Diff review for a daemon change includes any formula bump in the
  same PR.
- Anyone with this repo cloned can `brew install --formula
  integrations/homebrew-formula/beatsd.rb` to test a release without
  the tap being public.

## To wire up the tap repo (one-time)

1. Create a new public repo: `github.com/lanterno/homebrew-beats`.
2. In that repo, add `Formula/beatsd.rb` containing exactly the
   contents of `beatsd.rb` here. (The path matters — Homebrew taps
   look in `Formula/`.)
3. Tag a release on this repo. `v0.1.0` and `v0.1.1` are taken by tags
   from 2015 with no assets, so start at `v0.2.0`:
   `git tag v0.2.0 && git push origin v0.2.0`. The `Release Daemon`
   workflow (`.github/workflows/release-daemon.yml`) builds and uploads
   four tarballs (darwin+linux × arm64+amd64) with sha256 sidecars.
4. Put the version, URLs and SHA256 sums into the tap's
   `Formula/beatsd.rb` in place of the `PLACEHOLDER_*` lines, by hand or
   with `brew bump-formula-pr --url … --sha256 … Formula/beatsd.rb`.
5. Smoke-test:

   ```bash
   brew tap lanterno/beats
   brew install beatsd
   beatsd version
   beatsd pair <code>          # a 6-char code from the web's Settings → Daemon
   brew services start beatsd  # LaunchAgent on macOS, systemd user unit on Linux
   ```

## Bumping for new releases

Each future tag triggers `release-daemon.yml`; mirror the new `version`,
URLs and sha256 lines from its release into the tap's `Formula/beatsd.rb`.
That step is a copy-paste today (AHM-13 would automate it).

## Notes

- The formula's `service` block creates a macOS LaunchAgent
  (`~/Library/LaunchAgents/homebrew.mxcl.beatsd.plist`) or a Linux systemd
  user unit.
- The binary lands in `/opt/homebrew/bin` (Apple Silicon) or
  `/usr/local/bin` (Intel).
- It is not notarized, so on macOS Gatekeeper asks once; allow it in
  System Settings → Privacy & Security. Signing needs an Apple Developer
  account (AHM-14).
- No cask: `beatsd` is a CLI, not a `.app`. The Mac app's cask is a
  separate item (AHM-48).
