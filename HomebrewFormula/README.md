# Homebrew formula

This directory is the Homebrew tap for `beatsd`: it installs the daemon
without Go, and `brew upgrade` keeps it current.

```bash
brew tap lanterno/beats https://github.com/lanterno/beats
brew install beatsd
beatsd pair <code>          # a 6-char code from the web's Settings → Daemon
brew services start beatsd  # LaunchAgent on macOS, systemd user unit on Linux
```

The URL in `brew tap` is needed because the repo's name lacks the
`homebrew-` prefix Homebrew otherwise assumes. After it, `brew update`
follows `main`, and
`brew install lanterno/beats/beatsd` works as well as the bare name.

| File | What it is |
|------|------------|
| `beatsd.rb` | The formula, with the version and the four archive checksums of the latest release. |
| `bump.sh` | `bump.sh <version> <sidecar-dir> [formula]` rewrites the formula's version line and its four `sha256` lines from a release's `.sha256` sidecars. |

## Why the tap is this repo

The project is one repo while it has one developer, and the formula is no
exception. Homebrew looks for a tap's formulae in `Formula/`, then
`HomebrewFormula/`, then the repo root, so a formula in `HomebrewFormula/`
makes this repo a tap with nothing else to set up: the release workflow
commits to `main` with the run's own token. Homebrew reads only
the `*.rb` files here; this README and `bump.sh` are ignored. The cost is
that tapping clones the whole repo: about 11 MB to download, some 22 MB
on disk.

The formula is reviewed in pull requests like any other file. Only its
`version` line and the four `sha256` lines are the release's to write;
`bump.sh` finds each `sha256` on the line after the `url` that names its
archive, so keep those pairs together when editing.

## How a release reaches users

1. A `v*` tag is pushed. `.github/workflows/release-daemon.yml` builds the
   archives, each with a `.sha256` sidecar, and publishes the GitHub
   release.
2. Its `homebrew` job checks out `main`, not the tag, downloads the
   sidecars from the published release and runs `bump.sh` with them and
   the tag's version (without the `v`). The rest of the formula stays
   `main`'s, so a formula fix merged after the tag was cut survives the
   release.
3. It checks that every release URL the formula names serves the bytes its
   sidecar hashes, then installs the bumped formula from a throwaway tap —
   so from the published tarball — runs `brew test`, and checks
   `beatsd version` names the tag. A formula that fails any of these never
   reaches `main`.
4. It commits the formula as github-actions[bot]
   ("build(homebrew): beatsd 0.9.1") and pushes to `main`, rebasing and
   retrying if `main` moved meanwhile. If the rebase changed the formula
   (a pull request edited it while the job ran), the file is no longer the
   one tested, so the job fails instead of pushing; re-running it bumps and
   tests the new formula. Users get it on their next `brew update`.

A bot commit rather than a pull request: one opened with the run's
`GITHUB_TOKEN` triggers no CI and would wait on a human to merge a change
that is mechanical and already install-tested. The commit deploys nothing:
a push made with `GITHUB_TOKEN` triggers no workflow, and the API and SPA
deploys only fire on `api/**`, `terraform/**` and `ui/**`.

The job stops without a commit when `main`'s formula is already newer than
the tag (a rerun of an older release does not downgrade anyone) or already
names this release. Any rerun is safe, of the `homebrew` job alone or of
all jobs: it pushes the formula if an earlier attempt stopped short and
nothing otherwise. "Re-run all jobs" rebuilds the archives, which are not
byte-identical (tar records mtimes), but the release keeps the archives and
sidecars it first published (`overwrite_files: false`), and the job takes
its checksums from the release, not from the rebuild.

`.github/workflows/daemon.yml` checks every pull request that touches this
directory: `ruby -c`, `bump.sh` run on a copy with dummy sidecars (so a
formula `bump.sh` no longer matches fails in review, not at release), and
`brew style`.

## Cutting a release

```bash
git tag v0.9.1 && git push origin v0.9.1
```

Watch the *Release Daemon* run. Its *Homebrew formula* job goes green
either after pushing a `build(homebrew): beatsd 0.9.1` commit to `main` or
after logging why it left the formula alone (`main` already newer, or
already at this release), so look for that commit on `main`. Once it is
there:

```bash
brew update && brew upgrade beatsd
beatsd version                       # names the tag
```

A tag with a hyphen, such as `v1.0.0-rc.1`, is published as a GitHub
prerelease, never the repo's Latest release, and leaves the formula alone;
`bump.sh` takes only a plain `N.N.N`.

## Testing locally

Homebrew installs a formula only from a tap, never from a bare file. To
test the tap as users get it, tap the checkout itself; a local path works
as the remote and clones the committed `HEAD`:

```bash
brew tap beats-local/test "$(git rev-parse --show-toplevel)"
brew install beats-local/test/beatsd
brew test beats-local/test/beatsd
beatsd version
brew uninstall beats-local/test/beatsd
brew untap beats-local/test
```

To test an edited formula before committing it, or one bumped to another
release, copy it into a throwaway tap:

```bash
tag=v0.9.0
dir=$(mktemp -d)
gh release download "$tag" -R lanterno/beats -p 'beatsd-*.tar.gz.sha256' -D "$dir"
cp HomebrewFormula/beatsd.rb "$dir/beatsd.rb"
HomebrewFormula/bump.sh "${tag#v}" "$dir" "$dir/beatsd.rb"

brew tap-new --no-git "$USER/beats-test"
cp "$dir/beatsd.rb" "$(brew --repository "$USER/beats-test")/Formula/beatsd.rb"
brew style "$USER/beats-test/beatsd"
brew install "$USER/beats-test/beatsd"
brew test "$USER/beats-test/beatsd"

brew uninstall "$USER/beats-test/beatsd"
brew untap "$USER/beats-test"
brew developer off   # tap-new turns developer mode on; skip if you had it on
```

## Notes

- The formula's `service` block creates a macOS LaunchAgent
  (`~/Library/LaunchAgents/homebrew.mxcl.beatsd.plist`) or a Linux systemd
  user unit; `brew services start beatsd` starts it.
- The binary lands in `/opt/homebrew/bin` (Apple Silicon) or
  `/usr/local/bin` (Intel).
- The binary is not notarized. A `brew install` still runs it without a
  Gatekeeper prompt, since Homebrew quarantines cask downloads only, never a
  formula's. A copy downloaded by hand from the release page in a browser
  is quarantined: clear it with `xattr -d com.apple.quarantine beatsd`, or
  allow it in System Settings → Privacy & Security. Signing and
  notarization need an Apple Developer account (AHM-14).
- No cask: `beatsd` is a CLI, not a `.app`. The Mac app's cask is a
  separate item (AHM-48).
