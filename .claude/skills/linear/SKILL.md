---
name: linear
description: How work is tracked for this repo (LifePete / beats) in Linear. Use when the user names an issue ("AHM-17", "work on AHM-17", "pick up the Plan page bug"), asks what to work on next, when a task turns up a bug, follow-up or open question worth keeping, or when a PR or commit closes tracked work. Also use before writing a "Follow-ups", "Remaining" or "Open" section into any doc — that belongs in Linear instead.
---

# Linear for beats

All open work — bugs, follow-ups, open questions, external chores — lives in the
Linear project **lifepete** (team `AHM`):
https://linear.app/elghareeb/project/lifepete-a8ecce3a86de. The docs in `docs/`
and the READMEs hold decisions and designs only; never add a to-do list,
"Remaining" or "Follow-ups" section to them. Linear tools are `mcp__linear__*`
(server configured in `.mcp.json`; if they're missing, ask the user to run
`/mcp` and authenticate **linear**).

## Layout

- **Milestones** group the work: *Google Play launch*, *Homebrew tap*,
  *Project page follow-ups*, *Work contracts follow-ups*, *Companion: native &
  device*, *macOS*. Read a milestone's description before adding to it — some
  hold an intended order.
- **Labels**: one or more surfaces — `api`, `ui`, `companion`, `daemon`,
  `macos`; a blocker if any — `needs-device`, `needs-paid-credentials`,
  `external` (done by the account holder in a console, not in code); a kind —
  `Bug`, `Feature`, `Improvement`; `decision` for an open question.
- **States**: Backlog (someday) → Todo (next) → In Progress → In Review (PR
  open) → Done. Canceled keeps a cut idea with its reason, so it isn't proposed
  again without it.
- **Priority**: Urgent 1, High 2, Medium 3 (bugs), Low 4, None 0 (most ideas).

## Working an issue

1. `get_issue` — read the description and any doc section it cites. Check the
   code still matches; if the work has already shipped, say so, mark it Done
   with a comment naming the commit, and stop.
2. `save_issue` → state **In Progress**, assignee `me`.
3. Branch from an up-to-date `main`, named in the repo's style with the issue
   ID in it: `<type>/ahm-<n>-<short-slug>` (`fix/ahm-17-plan-week-utc`). The ID
   in the branch is what links the PR to the issue.
4. Implement, committing per the user's rules (code commit, then its test
   commit; frontend and backend never share a commit; one goal each). Put the ID
   at the end of each commit's subject: `fix(ui): the Plan page's week in local
   time (AHM-17)`.
5. Open the PR (the user merges; never push to `main`). Put `Fixes AHM-17` on
   its own line in the body — for several, one line each. Set the issue to
   **In Review** and add the PR as a link (`save_issue` `links`) unless the
   GitHub integration already did.
6. A PR that only partly covers an issue says `Part of AHM-17` instead, and the
   issue stays In Progress.

## Filing what you find

A bug, follow-up or open question that is out of scope for the current task
becomes an issue, not a TODO comment or a doc bullet. Before creating one,
`list_issues` with a `query` for it to avoid duplicates. Then `save_issue` with:

- `team: "AHM"`, `project: "lifepete"`, the fitting `milestone` (none if
  nothing fits — don't invent milestones without asking);
- a title that states the problem or outcome in plain words;
- labels as above; state Todo for a real bug, Backlog otherwise;
- a description that a stranger can act on: what is wrong or wanted, where
  (`path/to/file.ts:42`), why it matters, and where it came from.

Mention what you filed (ID + title) in your reply. File without asking when the
user asked you to track things; otherwise list the candidates and ask.

## What's next

When asked what to work on: `list_issues` for the project with `state: "Todo"`,
then sort by priority. Skip anything labelled `external` or `needs-*` unless the
user asks — those need the user, a device or an account, not code.
