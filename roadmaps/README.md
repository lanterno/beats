# Roadmaps

What is **not built yet**: the plan behind an epic, a design seed nobody has
started, a mockup of a design still being argued, a draft awaiting somebody's
review. [docs/](../docs/) is the other half — what is built, and why.

Three things that are **not** roadmaps:

- **Open work.** A bug, a follow-up, a question to decide: that is a
  [GitHub issue](https://github.com/lanterno/beats/issues), and these files
  link to issues rather than restating them. A file here says why the work is
  shaped the way it is; the issue says it is owed.
- **A decision not to build something.** "Left out of 1b" in
  [docs/billing.md](../docs/billing.md) reads like a to-do list and is the
  opposite of one: it records scope that was deliberately cut, so it is not
  re-argued. That belongs with the thing it was cut from.
- **Anything a code comment cites.** A comment describes what the code does,
  and what it does is built, so comments point at `docs/`.

When a subject ships, its file moves to `docs/` — or, if only part of it
ships, that part is deleted here and written there. It is never copied: two
accounts of one decision disagree the first time one is edited.

| File | What it covers |
|------|----------------|
| [organisations.md](organisations.md) | The organisations epic (#353): the four rules, why the stages went in the order they did, and the five deferred items with what each waits on |
| [billing.md](billing.md) | Invoices — the one unbuilt seed left from billing's phases |
| [legal/](legal/) | Drafts for #352, unreviewed by counsel: a data-processing agreement, a works-council sheet, a DPIA template |
