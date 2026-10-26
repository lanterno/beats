---
name: github-issues
description: How work is tracked for this repo (LifePete / beats) in GitHub issues. Use when the user names an issue ("#328", "work on 328", "pick up the pairing-code TTL bug"), asks what to work on next, when a task turns up a bug, follow-up or open question worth keeping, or when a PR or commit closes tracked work. Also use before writing a "Follow-ups", "Remaining" or "Open" section into any doc — that belongs in an issue instead.
---

# GitHub issues for beats

All open work — bugs, follow-ups, open questions, external chores — lives in the
issues of `lanterno/beats`: https://github.com/lanterno/beats/issues. The docs in
`docs/` and the READMEs hold decisions and designs only; never add a to-do list,
"Remaining" or "Follow-ups" section to them. Use the `gh` CLI (`gh issue list`,
`gh issue view`, `gh issue create`, `gh issue edit`); inside the checkout the repo
is implied. Until 2026-10-26 the tracker was Linear: its ids (`AHM-n`) survive in
older commit subjects and a few test comments, and every issue moved from it ends
with the id it came from.

## Layout

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

## Filing what you find

A bug, follow-up or open question that is out of scope for the current task becomes
an issue, not a TODO comment or a doc bullet. Before creating one, `gh issue list
--state all --search "<words>"` to avoid duplicates. Then `gh issue create` with:

- a title that states the problem or outcome in plain words;
- labels as above, and the fitting `--milestone` (none if nothing fits — don't
  invent milestones without asking);
- a body that a stranger can act on: what is wrong or wanted, where
  (`path/to/file.ts:42`), why it matters, and where it came from. Write it to a
  file and pass `--body-file`, so the Markdown keeps its lines.

Mention what you filed (number + title) in your reply. File without asking when the
user asked you to track things; otherwise list the candidates and ask.

## What's next

When asked what to work on: `gh issue list --state open --limit 100`, narrowed with
`--milestone` or `--label` when the user names one. Skip anything labelled
`external` or `needs-*` unless the user asks — those need the user, a device or an
account, not code. A `bug` comes before an `enhancement`, and an issue its
milestone's description puts first comes before the rest.
