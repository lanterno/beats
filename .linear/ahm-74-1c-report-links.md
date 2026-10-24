---
linear: unfiled
title: "Report links: a client reads its own hours without a login (phase 1c)"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, Feature]
state: In Progress
priority: 2
parent: AHM-74
---

The last piece of AHM-74's phase 1 ("Clients for freelancers"). 1a built
clients, dated rates and billable marks; 1b built billing budgets. Section 4 of
the epic lists one thing neither covers:

> Report links. Read-only, no login, a fixed date range, revocable, showing
> only that client's projects.

`docs/billing.md` already sketches it under *How later phases build on it*:

> **1c, report links.** A link names one client and a range, under a new public
> prefix, and is served by `assemble_client` with only that client's inputs,
> through an allowlist of what a client may see; amounts only when the link
> says so. It cannot structurally reach other clients, personal projects, flow,
> biometrics or the coach, and since running beats are left out it shows the
> same figures on every read.

## Why now

It needs no organisations, so it ships ahead of phase 2, and it sells to one of
the epic's two target groups on its own. It is also the first time any Beats
data reaches a reader with no session, which makes it the first real test of
the privacy wall the epic rests on.

## Scope

- A `report_links` collection: one client, a fixed `first`/`last`, the owner's
  `tz` frozen at creation, `show_amounts` and `show_entries`, a URL-safe token.
- `BillingService.client_period`, reading one client's inputs only and calling
  `assemble_client` — never `period`, which assembles every client.
- A public `/api/reports/{token}` prefix, rate-limited, `no-store`, `noindex`,
  answering a response schema written field by field rather than reusing
  `ClientBillingResponse`.
- Owner-side CRUD under `/api/clients/{id}/links`, and a Clients page panel to
  mint, copy and revoke.
- A public SPA route outside `ProtectedRoute`.

The design, with its decisions, goes in `docs/billing.md` under *Report links
(phase 1c)*.

## Done when

- A link serves one client's figures to a reader with no token, and the same
  figures on every read.
- A revoked, mistyped or expired-range link 404s, with no hint of which.
- A device token cannot reach the public prefix.
- The response cannot name another client, a personal project, a tag, a note,
  flow, biometrics or the coach — structurally, not by an allowlist someone has
  to remember.

## Built

On branch `feat/ahm-74-1c-report-links`, nine commits, all four boxes above
checked by tests. Set the issue to In Review when it is filed, and put
`Fixes AHM-<n>` in the PR body once it has a number.

Beyond the scope above, three things the work turned up:

- **PRIVACY.md had promised this feature's own disclosure** — "if sharing a
  report with a client is ever added … this page will say so before the release
  that adds it" — so it is updated, along with DATA.md's collection list.
- **The service worker would have cached a report** for five minutes despite
  the API's `no-store`, because the Cache Storage API does not read
  Cache-Control. A `NetworkOnly` route now sits before the generic `/api/` one.
- **The backup stays at 1.3**: report links are deliberately not exported, so
  no backup file carries a live URL to a year of someone's hours.

Two issues filed beside this one: [report-links-notes](report-links-notes.md)
and [ui-gen-types-broken](ui-gen-types-broken.md).
