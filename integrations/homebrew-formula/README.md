# Homebrew formula

Canonical home for the `beatsd` Homebrew formula. The file
`beatsd.rb` here is what gets copied into the eventual
`homebrew-beats` tap repo.

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

1. Create a new public repo: `github.com/<your-user>/homebrew-beats`.
2. In that repo, add `Formula/beatsd.rb` containing exactly the
   contents of `beatsd.rb` here. (The path matters — Homebrew taps
   look in `Formula/`.)
3. Tag a release on this repo: `git tag v0.1.0 && git push --tags`.
   The `Release Daemon` workflow at
   `.github/workflows/release-daemon.yml` builds and uploads four
   tarballs (darwin+linux × arm64+amd64).
4. Pull the SHA256 sums from the release artifacts and update the
   four `PLACEHOLDER_*` lines in `Formula/beatsd.rb` on the tap
   repo. (Or use `brew bump-formula-pr` — see
   `docs/homebrew-tap.md`.)
5. Users now install via:

   ```bash
   brew tap <your-user>/beats
   brew install beatsd
   beatsd pair <code>
   brew services start beatsd
   ```

## Bumping for new releases

Each future tag from this repo:

1. Triggers `release-daemon.yml` → produces tarballs + sha256
   sidecars on the GitHub release.
2. Mirror the new `version`, URLs, and sha256 lines from this file
   into the tap's `Formula/beatsd.rb`.

A small follow-up workflow could automate step 2; today it's a
copy-paste.
