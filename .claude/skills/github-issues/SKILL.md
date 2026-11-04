---
name: github-issues
description: How work is tracked for this repo (LifePete / beats) — the GitHub issues already filed, and since 2026-11-04 the Work sections and files in roadmaps/ where new work is written. Use when the user names an issue ("#328", "work on 328", "pick up the pairing-code TTL bug"), asks what to work on next, when a task turns up a bug, follow-up or open question worth keeping, or when a PR or commit closes tracked work. Also use before writing a "Follow-ups", "Remaining" or "Open" section into any doc — in docs/ that is a mistake, and in roadmaps/ it is a Work section.
---

# GitHub issues for beats

Open work lives in two places.

- **New work is written in `roadmaps/`**, not filed as an issue (decided
  2026-11-04; `roadmaps/README.md` § *What belongs here*). What a plan still owes
  goes under that plan's *Work* section, step by step; a bug or follow-up that
  belongs to no plan gets a file of its own there.
- **The issues already filed** in `lanterno/beats`
  (https://github.com/lanterno/beats/issues) stay open until they are done, and
  roadmaps cite them by number.

The docs in `docs/` and the READMEs hold decisions and designs only; never add a
to-do list, "Remaining" or "Follow-ups" section to them. Use the `gh` CLI (`gh issue list`,
`gh issue view`, `gh issue create`, `gh issue edit`); inside the checkout the repo
is implied. Until 2026-10-26 the tracker was Linear: its ids (`AHM-n`) survive in
older commit subjects and a few test comments, and every issue moved from it ends
with the id it came from.

## Layout

This layout is the issues'.

- **Milestones** group the work: *Google Play launch*, *Homebrew tap*, *Companion:
  native & device*, *macOS*. Read a milestone's description before adding to it —
  some hold an intended order. The organisations epic is an issue, #353, with what
  it still owes as a task list of child issues.
- **Labels**: one or more surfaces — `api`, `ui`, `companion`, `daemon`, `vscode`,
  `wall-clock`, `macos`, `infra`, `ci`, `docs`; a blocker if any — `needs-device`,
  `needs-paid-credentials`, `external` (done by the account holder in a console,
  not in code); a kind — `bug`, `enhancement`; `decision` for an open question.
  `needs-triage` and `good first issue` are for issues from the public, and the
  labeler workflow stamps surfaces on PRs by the files they touch.
- **State**: open or closed. An idea that was cut is closed as *not planned* with
  its reason in the body, so it isn't proposed again without it. An open PR whose
  body says `Fixes #n` is what "in progress" looks like.
- **Priority**: not a field. An issue that must come next says so in its first
  line; otherwise the milestone's description gives the order.

## Working an issue

1. `gh issue view <n>` — read the description and any doc section it cites. Check
   the code still matches; if the work has already shipped, say so, close it with a
   comment naming the commit, and stop.
2. Branch from an up-to-date `main`, named in the repo's style with the issue
   number in it: `<type>/<n>-<short-slug>` (`fix/328-pairing-code-ttl`).
3. Implement, committing per the user's rules (code commit, then its test commit;
   frontend and backend never share a commit; one goal each). Commit subjects carry
   no issue number — `fix(api): pairing codes expire on a BSON date` — because a
   `(#n)` in a subject is where merges put the PR number. The branch and the PR
   body carry the issue.
4. Open the PR (the user merges; never push to `main`). Put `Fixes #n` on its own
   line in the body — for several, one line each. GitHub links the PR to the issue
   from then on and closes the issue when the PR merges into `main`, so don't close
   it by hand.
5. A PR that only partly covers an issue says `Part of #n` instead; merging it
   leaves the issue open. When a child of an epic closes, tick its box in the
   epic's task list.

## Working a roadmap step

The same loop without a number. Branch `<type>/<short-slug>`; the PR body names
the file and the item (`roadmaps/backoffice.md`, a Work bullet) where an issue would have
`Fixes #n`. When the step ships, its part of the roadmap is deleted and what was
built, and why, is written into `docs/`, in a commit of its own
(`roadmaps/README.md` § *When something ships*).

## Writing down what you find

A bug, follow-up or open question that is out of scope for the current task is
written down, not left as a TODO comment or a bullet in `docs/`. Don't file a new
issue for it.

- If it belongs to a plan, it goes into that roadmap's *Work* section. If it
  belongs to none, it gets a file of its own in `roadmaps/` and a row in
  `roadmaps/README.md`'s table.
- First check it isn't already there: `git grep -n "<words>" roadmaps/` and
  `gh issue list --state all --search "<words>"`.
- Write it for a stranger: what is wrong or wanted, where (`path/to/file.ts:42`),
  why it matters, and where it came from. A new file opens with what it blocks
  and what blocks it (`roadmaps/README.md` § *Writing for whoever picks this up*).

Mention what you wrote down (file and section) in your reply. Write it without
asking when the user asked you to track things; otherwise list the candidates and
ask.

## What's next

When asked what to work on: the *Work* sections in `roadmaps/`, whose first
screens say what blocks each, and `gh issue list --state open --limit 100`, narrowed
with `--milestone` or `--label` when the user names one. Skip anything labelled
`external` or `needs-*` unless the user asks — those need the user, a device or an
account, not code. A `bug` comes before an `enhancement`, and an issue its
milestone's description puts first comes before the rest.
