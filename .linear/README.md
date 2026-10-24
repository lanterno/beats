# Linear queue

Work that belongs in Linear but was written while the Linear MCP server was
unauthenticated. Each file here is one issue, ready to be transcribed into the
`lifepete` project (team `AHM`) and then deleted from this directory.

This is a staging area, not a second tracker. Nothing here is a source of
truth: once an issue exists in Linear, delete its file and let Linear hold it.
Decisions and designs still go in `docs/` and the READMEs, exactly as
`CLAUDE.md` says — a file here holds only what Linear would hold.

## Syncing

With the `linear` MCP server authorized (`/mcp` in an interactive session):

1. For each file, `list_issues` with a `query` from its title, to avoid
   creating a duplicate of something filed in the meantime.
2. `save_issue` with the frontmatter's fields and the body below it.
3. Replace the file's `linear:` field with the issue ID it got, or delete the
   file outright. An issue that is already Done needs no file.

## Frontmatter

The keys map one-to-one onto `save_issue`:

```yaml
---
linear:      # the issue ID once filed, else "unfiled"
title:       # the issue title
team: AHM
project: lifepete
milestone:   # or "none" — don't invent milestones
labels: []   # surface (api, ui, …), kind (Bug, Feature, Improvement), decision
state:       # Backlog | Todo | In Progress
priority:    # Urgent 1 | High 2 | Medium 3 | Low 4 | None 0
parent:      # the epic or parent issue, if any
---
```
