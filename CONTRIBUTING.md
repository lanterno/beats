# Contributing to LifePete

Thanks for wanting to help. LifePete is one maintainer's project
([@lanterno](https://github.com/lanterno)), open source under MIT, and also run as a
hosted service at [lifepete.com](https://lifepete.com). Everything the hosted service
runs is in this repository.

## Where things go

- **A bug** — [open an issue](https://github.com/lanterno/beats/issues/new/choose). The
  form asks where it happens and how to reproduce it.
- **An idea** — start a thread in
  [Discussions → Ideas](https://github.com/lanterno/beats/discussions/categories/ideas).
  Ideas become tracked work once it's clear they fit.
- **A question** — [Discussions → Q&A](https://github.com/lanterno/beats/discussions/categories/q-a).
- **A security problem** — privately, as [SECURITY.md](SECURITY.md) describes. Never in
  an issue.

The maintainer plans the work in this repo's issues too, so an issue you open sits
beside the rest. Commits from before late October 2026 end in IDs like `(AHM-17)`:
that was Linear, since moved here.

## Before you write code

For anything larger than a small fix, say what you intend in the issue or idea first,
so you don't spend a weekend on something that won't be merged. Small fixes — a typo, a
broken link, an obvious bug with a test — can go straight to a pull request.

## Setting up

The [README](README.md#getting-started) gets each part running, and
[CLAUDE.md](CLAUDE.md) is the full developer guide: every command, how each surface is
tested, and the conventions. (It is written for AI coding assistants and people alike.)
The [devcontainer](.devcontainer/devcontainer.json) has every toolchain installed.

Install the hooks once, from the repo root:

```bash
lefthook install
```

They lint and type-check what you stage on every commit and run the full test suites
of the surfaces you touched before every push, the same checks CI runs.

## Commits

A reviewer should be able to check each commit for one thing:

- **One goal per commit.** A refactor, a behaviour change, a dependency bump, generated
  files and docs each get their own.
- **Tests in their own commit,** right after the code they cover.
- **Frontend and backend never share a commit.** A change that spans both is one commit
  per side.

Subjects follow the history's style: `fix(ui): the Plan page's week in local time`.

## Tests

Write the test that would fail if the thing were broken, not the one that fails when it
is merely different. [What to test, and what not to](CLAUDE.md#what-to-test-and-what-not-to)
explains the difference, with examples from this codebase.

## Two deployments

The same code runs self-hosted on one origin and at lifepete.com on two (Firebase
Hosting and Cloud Run, joined by CORS). A change to origins, hosts, auth cookies or a
deploy pipeline has to work for both; see Infrastructure in [CLAUDE.md](CLAUDE.md#infrastructure).

## Licence

By contributing you agree that your work is released under the [MIT licence](LICENSE).
