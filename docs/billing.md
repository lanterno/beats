# Clients and Billing

> Beats records what you worked on. For freelance work this makes it able
> to say what that work is *worth*: on the last day of the month, what is
> billable to each client, at what rate, and what it comes to — in the
> client's own currency, adding up to the cent, as an invoice does.

A **client** is someone you bill: a record in your own account with a
name, an optional contact, one ISO 4217 currency and a dated default rate.
A freelance project's **billing** ties it to one client under dated
**terms**, each saying from which day its hours are billable and,
optionally, at a rate of the project's own. A **billable override** marks
one entry billable or not, whatever its project's term says. From those
and the finished sessions, Beats works out a month's figures per client.

The decisions below were made in the design of phase 1a of Organisations
(AHM-88) and are recorded so that later work does not re-litigate them.
The rest says what was built on them and why. Phase 1b, billing budgets
(AHM-95), has a section of its own, *Billing budgets (phase 1b)*: it builds
on these decisions and changes none of them. How the project page shows a
project's billing is in [project-page.md](project-page.md).

---

## Decisions

1. **A client is a record in your own account.** Not an account of
   theirs, not an organisation: nothing is shared with a client, and a
   client sees nothing. Phase 2 can link "my client Acme" to an Acme
   organisation without moving the record.
2. **Billing lives in its own collections**, `clients`, `project_billing`
   and `billable_overrides`, under its own routes, `/api/clients` and
   `/api/billing`. Nothing is a field of `Project` or of `Beat`, for four
   reasons, each checked against the code:
   - **Devices.** `DEVICE_ALLOWED_PREFIXES` in `server.py` matches
     `/api/timer`, `/api/projects` and `/api/beats` by prefix, and the
     timer's status hands a paired device the project document whole. Two
     prefixes that match neither keep every figure off every device.
   - **Replace-style writes erase fields.** `PUT /api/projects/` falls back
     to the request's defaults for a key left out; `PUT /api/beats/`
     rebuilds a fresh `Beat` and replaces the stored one; `stop_timer`
     reads the beat, awaits its flow tags, then replaces it, so a flag
     written in between would be lost; an older SPA tab's Zod schema strips
     keys it does not know. A collection with one writer is out of reach of
     all four.
   - **Phase 2.** Organisations will read the projects and beats they own.
     A contractor's client, rates and marks, in collections scoped only by
     the contractor's `user_id`, stay on the far side of a collection
     boundary, rather than behind a serialiser allowlist someone must
     remember to keep.
   - **The coach** reads projects and sessions through `CoachRepos` and
     formats the fields it chooses. It has no port to these collections and
     so cannot see them.
3. **Only a freelance project is billed** (409 `NOT_FREELANCE` otherwise),
   and a billed project keeps its kind: moving it away from freelance is
   refused (409 `PROJECT_HAS_BILLING`) until its billing is stopped. It
   mirrors a contract living only on a day job: no dormant money on a
   project that cannot read it. Loosening the rule later breaks nothing.
4. **Dated terms carry both the flag and the rate.** "Not billable from 1
   November" is a term, so October's figures stay as they were. Before a
   project's first term nothing of it is billable, unless an override says
   so.
5. **The resolution order.** The flag: the entry's override, else the
   project's term in force that day, else not billable. The rate: the
   term's own rate, else the client's rate in force that day, else none —
   the hours are then billable but *unpriced*. Both levels are dated, and
   neither reaches back before its first term.
6. **Money is integer minor units**, in one currency per client: cents for
   EUR, yen for JPY, fils for KWD. No float holds an amount anywhere, in
   storage, on the wire or in the SPA. The number of minor units comes from
   one place, the API's table (`domain/currencies.py`): the browser's ICU
   data disagrees with ISO on some codes, HUF and IQD among them, so every
   amount the API sends carries `minor_units` beside `currency`. One
   currency per client, rather than per rate, keeps a client's figures, and
   later its money budgets, in one currency without an exchange rate.
7. **A report line is a run of consecutive days** of one project at one
   rate from one source, and it is rounded once: its hours to 0.01 h, its
   amount to a whole minor unit, both half-up. So on every line the printed
   hours times the printed rate is the printed amount, and every total is a
   sum of lines. Rounding per entry would drift over many entries, and an
   invoice has no per-day lines to round on. Runs, not groups by rate
   value, so 85 → 95 → 85 is three lines, and a client rate equal to a
   project rate is two.
8. **The local day an entry started on decides everything**: its month and
   its rate, in the request's timezone, which is required. It is the rule
   the ledger and the timesheet already follow. A UTC default would move
   evening work in the Americas, and early-morning work east of Greenwich,
   into the wrong month.
9. **A running timer is not billed.** A billed figure must not move between
   two reads with no edit between them, and a bill records finished work.
   The ledger and the timesheet count a running beat up to now on purpose;
   billing differs, and the client's `running` flag lets the page say so.
10. **The client link is not dated.** A project is for one client, and
    moving it moves all of its hours, which is a change to the past. A
    project whose client really changed is a new project.
11. **Nothing retroactive without consent, checked by the server.** A write
    that would change figures before the 1st of the current month, in the
    request's timezone, needs `rewrite_past: true`, or the API answers 409
    `RETROACTIVE_CHANGE`. Consent that lived only in the UI could be
    bypassed by a stale tab or a script.
12. **A client's currency is locked once anything is priced in it**: a rate
    of the client's, or a rate of the project's own on a project billed to
    it (409 `CURRENCY_IN_USE`). A typo made at creation can still be fixed
    before then.
13. **Archive, not delete.** A client is deleted only while no project is
    billed to it (409 `CLIENT_HAS_PROJECTS`). Archived, it keeps its name
    and currency in the months it has hours in.
14. **The privacy wall** is the collection boundary of Decision 2, the two
    prefixes no device token reaches, and a coach with no port to them.
    Budgets, report links and organisations extend it without moving data
    (see *Billing budgets (phase 1b)* and *How later phases build on it*).
15. **Naming.** Phase 1b's limits are *billing budgets*, never "budgets"
    alone: `WeeklyPlan.budgets` already means a week's planned hours per
    project.

Left out of 1a, each addable later without migrating data: tax (amounts
are net), invoices, billing increments (time is billed exactly, to
0.01 h), exchange rates, unique client names, billing columns in the
sessions CSV, a separate client details page, notes in the report.

---

## Data model

All three collections are user-scoped through `MongoStore`, which adds
`user_id` to every query and stamps it on every write, and they are
stored in JSON form (dates as ISO strings), as every collection but
`timeLogs` is. The models are in `domain/models.py`, beside `Contract`.

```python
RATE_MINOR_MAX = 100_000_000   # 1,000,000.00/h in a two-decimal currency

class RateTerm:                 # one stretch of a client's default rate
    effective_from: date        # any day of the week: rates change on invoice dates
    rate_minor: int             # strict, > 0, <= RATE_MINOR_MAX: 85.5 and true are 422s

class Client:                   # collection `clients`
    id: str | None
    name: str                   # stripped, 1-120 characters
    contact_name: str | None    # the same
    contact_email: str | None   # one "@" with text either side, <= 254; shown, never mailed
    currency: str               # three capitals: the shape only, see below
    rates: list[RateTerm]       # strictly ascending, one a day
    archived: bool
    created_at: datetime

class BillingTerm:
    effective_from: date
    billable: bool              # strict
    rate_minor: int | None      # as RateTerm's; refused on a term that is not billable

class ProjectBilling:           # collection `project_billing`, one per project
    project_id: str
    client_id: str
    terms: list[BillingTerm]    # strictly ascending, one a day

class BillableOverride:         # collection `billable_overrides`, one per beat
    beat_id: str
    billable: bool              # strict
```

- **The list rules are field validators**, so a 422's `fields` names
  `rates` or `terms`, and the rate rule names `terms.N.rate_minor`. A list
  out of order is refused, never sorted: sorting would quietly pick which
  of two same-day terms wins. The rate rule reads `billable` with
  `info.data.get`, so when `billable` itself failed, its own error stands.
- **`RATE_MINOR_MAX`** keeps every figure a JavaScript number can hold: a
  month of every hour at it, 1e8 × 744, is about 7.4e10, far inside 2⁵³.
- **The write bodies are the domain's fields.** `ClientFields` and
  `ProjectBillingFields` make every key required, null where it may be: a
  write replaces the record whole, and a key an older client leaves out
  must be refused, not read as cleared. `Client` and `ProjectBilling`
  subclass them and restore the defaults, since a stored `None` is left
  out of the document.
- **Indexes** (`ensure_indexes`): `clients (user_id)`; `project_billing
  (user_id, project_id)`, unique, so a second billing on a project
  replaces the first, and `(user_id, client_id)` for the reads that ask
  what is billed to a client; `billable_overrides (user_id, beat_id)`,
  unique. `timeLogs (user_id, project_id, start)` serves the month's range
  read, and every per-project read before it.

### Rules checked at write time, not on the model

A model is re-validated on every read. A rule there that later started
failing would make every stored record unreadable, which is why
`_check_contract` and `check_region` sit in the service, and these do too
(`domain/billing_service.py`).

- **The currency is known.** `domain/currencies.py` is a hand-kept table of
  the circulating ISO 4217 codes and their minor units. Funds, precious
  metals and test codes are left out: nobody bills an hour in them. A code
  it does not know is 400 `UNKNOWN_CURRENCY`, as an unknown holiday region
  is. A code that leaves circulation moves to the table's withdrawn list,
  never out of the module: a new client cannot pick it, and a client
  already priced in it still reads, with the same minor units. So the
  stored currency is not checked again when a client is updated; only a
  new one is, and the client dialog keeps offering a client its own.
- **The currency is locked once priced** (Decision 12), and once a money
  billing budget on the client, or on a project billed to it, is in it
  (phase 1b). `ClientResponse` carries `currency_locked` so the picker can
  say so before the user tries.
- **A client with billed projects** cannot be deleted (Decision 13). One
  that can takes its billing budget with it.
- **A project's billing**: the project is the caller's (404) and freelance
  (409 `NOT_FREELANCE`); the client is the caller's (404
  `CLIENT_NOT_FOUND`), archived or not, since a restored backup may bill
  an archived client. A move to a client in another currency is refused
  (409 `CURRENCY_MISMATCH`) while the project has a money billing budget,
  whose limit was set in the old currency (checked first, so the refusal
  names it), or while the terms it would have there carry a
  rate of the project's own, which was entered in the old currency, or a
  billable term dated before the current month, whose hours were billed in
  it, or while an entry before the current month is marked billable, for
  the same reason. Terms that drop both, with no such mark, move nothing,
  so they pass: to really change currency, stop billing and attach the
  project again, or start a new project.
- **The kind guard** sits in `ProjectService.update_project`, which
  `restore_project` goes through too, behind the narrow `BillingPresence`
  port. It reads billing only when the project is not freelance after the
  write, so the colour picker on a freelance project costs nothing.
- **An override** is allowed on any of the caller's own beats (404 for
  someone else's, or a malformed id) and counts only while the beat's
  project is billed. Moving a beat to another project keeps it: a mark is a
  fact about the entry. `BeatService.delete_beat` deletes the beat's
  override through the `BillableOverrideRemover` port, whether or not the
  beat was there, since an override left without its beat is a leftover
  either way.

---

## The arithmetic

All of it is pure, in `domain/billing.py`: no clock and no reads. The
service fetches, the assembler counts.

### Resolution

For a finished beat on a billed project, with `d` the local day it
started on:

```
term     = the project's term in force on d             (none before the first)
billable = the override on the beat, if there is one
           else term.billable, else False
rate     = term.rate_minor, if the term has one          source "project"
           else the client's rate in force on d          source "client"
           else none: unpriced                           no rate, no source
```

`in_force_on` is the latest term whose `effective_from` is not after the
day, as `Contract.term_on`. An override of `true` before the project's
first term is billed at the client's rate in force that day; an override
of `false` under a billable term drops the entry. A project with no
billing — a day job, a side project, a freelance project with no client
yet — is not in billing at all.

### Bucketing

- **The range** is the 1st of the month through its last day, or through
  today in `tz` while the month runs (month to date). A later month is 409
  `MONTH_NOT_STARTED`; a month with nothing in it is an empty report.
- **The read** is local midnight on the first day to local midnight after
  the last, converted to UTC with `zoneinfo`, so a DST change between
  needs nothing special (`utc_range`). `list_started_between` reads the
  beats of every billed or freelance project started in it; the assembler
  checks each beat's local day again, so the bucketing rule lives in one
  place.
- **A beat belongs whole to the day it started on.** One from 23:00 on 31
  October to 01:30 on 1 November is October's, at 31 October's rate.
- **Durations** are `end − start` taken in UTC, to the microsecond. Two
  datetimes in one zone subtract on the wall clock, which would lose or
  gain the hour the clocks change by; in UTC a 23- or 25-hour day is its
  real length.
- **A running beat** is left out, and sets its client's `running` when it
  would itself be billable.
- **A beat that ends before it starts**, which `POST /api/beats/` and a
  restore both take, is no time worked: it is left out of the lines, the
  entries and `unattached`, rather than taking hours, and money, off the
  beats beside it.

### Lines and rounding

- **A line** is a maximal run of consecutive days in the range over which
  one project's `(rate_minor, source)` holds, kept when billable entries
  fall in it. The runs are computed over the days themselves, at most 31
  lookups a project. `first` and `last` are the run's days within the
  range. An unpriced run is a line whose `rate_minor`, `source` and
  `amount_minor` are null.
- **Per line**, with `Decimal` and `ROUND_HALF_UP` (never Python's `round`,
  which rounds half to even, and so would make 18 s 0 h):
  1. the exact sum of its billable entries, in microseconds;
  2. `hours` = that sum in hours, quantized to 0.01;
  3. `amount_minor` = `hours × rate_minor`, quantized to a whole minor
     unit, or null when unpriced.

  12 h 20 m is 12.33 h; at 86.50 EUR, 12.33 × 8650 = 106 654.5 minor
  units, which is 106 655, or €1,066.55.
- **A client's figures are sums of its lines**: `billable_hours` is every
  line's hours, priced or not; `unpriced_hours` the unpriced lines' (a part
  of `billable_hours`); `amount_minor` the priced lines' amounts, 0 when
  none is priced. Only `non_billable_hours` is rounded on its own, once,
  from its exact sum. The report adds up to the minor unit, stricter than
  the ledger's "within 0.025" on purpose.
- **Each currency is totalled on its own**: `totals` has one row per
  currency in which a listed client has a line, and no figure anywhere
  holds two currencies.

### What the report lists

- Every active client, with hours or without, and an archived client with
  entries in the range. By name.
- A client's lines by project name, then `first`; its entries — every
  finished beat of its billed projects in the range, billable or not, by
  start. An entry's `hours` is for display; the lines are the figures. An
  entry's `overridden` says a mark decides it, not the project's term.
- Archived projects that have hours. A billing whose project no longer
  exists is skipped: it has no name to report under.
- `unattached`: every freelance project, archived or not, with finished
  hours in the range and no billing. Those hours are in no figure, and the
  page says so.
- No notes and no tags. Whether a client's report shows notes is a
  decision for report links.

`assemble_client` takes one client's inputs only — its billings, their
projects, their beats and those beats' overrides — and `assemble_billing`
maps it over the clients and adds the totals and `unattached`. A reader of
one client cannot reach another's.

### The closed past

The *closed past* is every day before the 1st of the current month in the
request's `tz`. `past_change(old, new, month_start)` compares two term
lists and reads no beats: it keeps the terms of each dated before
`month_start`, and answers the earliest date at which the two differ — a
term added, removed, or changed in its rate, its flag or its date — or
none. `link_change(terms, month_start)` is the earliest term dated before
it, for a write that moves every term at once. Such a write also moves
every entry marked billable, which an override bills whatever the terms
say, before the first term too: `marked_change` is the earliest day before
`month_start` that one of the project's entries marked billable started on.
It is the one check that reads beats, and only when some override marks
an entry billable: the overrides first, a small set, then the project's
beats before the month.

| Write | Gated from |
|---|---|
| `PUT /api/clients/{id}` | `past_change` over the client's rates |
| `PUT /api/billing/projects/{id}`, same client | `past_change` over the terms |
| the same, another client | the earliest of that, `link_change` over the old and the new terms together, and `marked_change` |
| `DELETE /api/billing/projects/{id}` | the earlier of `link_change` over the stored terms and `marked_change` |

Not gated: attaching a project the first time (no figure existed, and the
"Billable from" day the user sees and picks is the consent), an override
(editing a past entry is itself the consent) and an import (a restore puts
back what was). The current month is never gated: it has not been
invoiced. False positives are accepted — a past term may differ with no
hours under it — and they cost one confirmation. An "invoiced through"
date can later replace the month boundary without changing any request.

The refusal names the first month it touches: *"This changes billable
figures from March 2026, which may already have been invoiced. Confirm to
apply it."*

---

## HTTP contract

Every route needs a session token, and none sits under a device prefix: a
device token gets 403 on all of them, and the comment beside
`DEVICE_ALLOWED_PREFIXES` says never to add them, nor to put billing under
`/api/projects` or `/api/beats`. Someone else's client, project or beat is
not found (404), never forbidden, and so is a malformed id.

### `/api/clients`

| Method | Path | Body, params | Answers |
|---|---|---|---|
| GET | `/api/clients/?archived=false` | | the active clients, or the archived ones, by name |
| POST | `/api/clients/` | `ClientWriteRequest` | 201; 400 `UNKNOWN_CURRENCY`; 422 |
| GET | `/api/clients/{id}` | | 404 `CLIENT_NOT_FOUND` |
| PUT | `/api/clients/{id}?tz=` | `ClientUpdateRequest`: the same keys and `rewrite_past` | 409 `CURRENCY_IN_USE`, `RETROACTIVE_CHANGE`; 400; 422 |
| POST | `/api/clients/{id}/archive`, `/unarchive` | | the client |
| DELETE | `/api/clients/{id}` | | 204, and the client's billing budget goes too; 409 `CLIENT_HAS_PROJECTS` |

A write sends every key, null where it may be: `name`, `contact_name`,
`contact_email`, `currency`, `rates`. A client comes back with
`minor_units` and `currency_locked` beside its fields. An update replaces
the name, the contact, the currency and the rates; the archive flag and
the creation date stay as stored.

### `/api/billing`

| Method | Path | Body, params | Answers |
|---|---|---|---|
| GET | `/api/billing/projects` | | every project's billing, with its client's `currency` and `minor_units` |
| PUT | `/api/billing/projects/{project_id}?tz=` | `{client_id, terms, rewrite_past}`, all required | 404 project; 404 `CLIENT_NOT_FOUND`; 409 `NOT_FREELANCE`, `CURRENCY_MISMATCH`, `RETROACTIVE_CHANGE`; 422 `terms.N.rate_minor` |
| DELETE | `/api/billing/projects/{project_id}?tz=&rewrite_past=&remove_billing_budget=` | all three required | 204, the project's billing budget with it; 404 when it is not billed; 409 `PROJECT_HAS_BILLING_BUDGET`, `RETROACTIVE_CHANGE` |
| GET | `/api/billing/entries` | | every override, `{beat_id, billable}`: they are exceptions, so few |
| PUT | `/api/billing/entries/{beat_id}` | `{billable}`, strict | the override; 404 when the beat is not the caller's |
| DELETE | `/api/billing/entries/{beat_id}` | | 204, always: with no mark, or no beat, there is nothing left to clear |
| GET | `/api/billing/month?month=YYYY-MM&tz=` | both required | the month; 422; 409 `MONTH_NOT_STARTED` |
| GET | `/api/billing/budgets?tz=` | `tz` required | every billing budget, read as of today in `tz`; `[]` when none (see *Billing budgets*) |
| PUT | `/api/billing/budgets/clients/{client_id}` | `BillingBudgetRequest`, every key required | the budget, with `client_id`, `currency` and `minor_units`; 404 `CLIENT_NOT_FOUND`; 422 naming the key |
| PUT | `/api/billing/budgets/projects/{project_id}` | the same | the same; 404 project; 409 `BILLING_BUDGET_NEEDS_BILLING`; 422 |
| DELETE | `/api/billing/budgets/clients/{client_id}`, `/projects/{project_id}` | | 204, always: with no budget there is nothing left to clear |

```jsonc
// GET /api/billing/month?month=2026-10&tz=Europe/Berlin
{ "month": "2026-10", "first": "2026-10-01", "last": "2026-10-17",
  "totals": [{ "currency": "EUR", "minor_units": 2, "billable_hours": 41.5,
               "unpriced_hours": 0.0, "amount_minor": 352750 }],
  "clients": [{
    "client_id": "…", "name": "Studio Kite", "archived": false, "currency": "EUR",
    "minor_units": 2, "running": false, "billable_hours": 41.5,
    "non_billable_hours": 3.25, "unpriced_hours": 0.0, "amount_minor": 352750,
    "lines": [{ "project_id": "…", "project_name": "Website", "rate_minor": 8500,
                "source": "client", "first": "2026-10-01", "last": "2026-10-14",
                "hours": 30.0, "amount_minor": 255000 }],
    "entries": [{ "beat_id": "…", "project_id": "…", "day": "2026-10-02",
                  "start": "…Z", "end": "…Z", "hours": 2.5, "billable": true,
                  "overridden": false, "rate_minor": 8500 }] }],
  "unattached": [{ "project_id": "…", "name": "Logo refresh", "hours": 4.0 }] }
```

Hours are to the hundredth. The API works them in `Decimal` and declares
them `float` only in the response schemas, so they go out as numbers
(`41.5`), not strings. An entry's `rate_minor` is null when it is not
billable, or unpriced.

`GET /api/meta/currencies` lists `{code, minor_units}` for every code a
client may pick, cacheable for a day like the holiday regions. The SPA
names each code itself, with `Intl.DisplayNames`.

### What does not change

`/api/projects`, `/api/beats`, `/api/timer`, `/api/device`, the webhooks
and the daemon's routes keep their shapes byte for byte, and the
companion, the daemon, the editor extension and the wall clock see
nothing new. Two existing routes gain behaviour: `PUT /api/projects/` and
the import refuse a kind change on a billed project (409
`PROJECT_HAS_BILLING`, a new code on an unchanged shape), and `DELETE
/api/beats/{id}` removes the beat's override too.

---

## Backup 1.3

`GET /api/export/full` is version `1.3`. Since 1.2, beside the projects,
sessions, absences and adjustments it carries `clients` (archived ones
too, ids kept), `project_billing` and `billable_overrides`; 1.3 adds
`billing_budgets`, every budget whose scope still exists (a client, or a
project that is still billed), archived scopes included. The sessions CSV
does not change: its columns are a contract with spreadsheets, and billing
has its own report. Every list may be missing from a file, so a 1.0 or 1.1
backup imports as one with no billing, and a 1.2 one as one with no
budgets. An import writes and never deletes, so the account's own budgets
survive a file without them.

The import checks the whole file before writing anything:

1. A record that does not parse is a 422, a client's id included (24
   hexadecimal digits, since it is kept).
2. A project, a session or a client whose id is another account's is 409
   `BACKUP_OF_ANOTHER_ACCOUNT`.
3. Each billing's project and client, each override's session, and each
   billing budget's client or project, must be in the file or the account;
   otherwise a 422 names the record (`project_billing.0.client_id`,
   `billing_budgets.0.scope_id`).
4. A dry run of the client and billing writes' rules over the file laid on
   the account (`BillingService.check_restore`): a currency the table does
   not know, on a client that is new or whose currency changes; a currency
   changed once priced (`CURRENCY_IN_USE`); billing on a project that is
   not freelance as the file leaves it (`NOT_FREELANCE`); a billed project
   the file moves away from freelance without billing it anew
   (`PROJECT_HAS_BILLING`); billing moved to a client in another currency
   (`CURRENCY_MISMATCH`), the file's sessions and billable marks laid on
   the account's for the marks it counts. The budget rules run in the same
   pass: a project budget on a project that neither the file nor the
   account bills (`BILLING_BUDGET_NEEDS_BILLING`, named
   `billing_budgets.N`); a client currency the file changes while a money
   budget of the account's is in it (`CURRENCY_IN_USE`, named `clients.N`);
   billing the file moves to a client in another currency while the
   account's money budget on that project would survive
   (`CURRENCY_MISMATCH`, named `project_billing.N`). An account budget the
   file carries a budget for, on the same scope, is replaced by it and
   counts in neither check: a file's own money budget was set under the
   file's client, so it agrees with the billing the file restores. The
   first refusal is the route's own error, its detail naming the record
   (`project_billing.0: Only a freelance project is billed`). The
   retroactive gate is not applied.

Then the writes, in this order: clients, kept ids and archive flags
included; projects, each an ordinary project write; each project's
billing; billing budgets, each replacing the one on its scope; sessions;
overrides; then absences and adjustments as before. Billing, budgets
included, is never added to `skipped`: its rules ran before the first
write, and the deployed toast counts every skip that is not an absence as
a balance adjustment, so a new kind of skip would mislabel it during a
deploy. `imported` gains `clients`, `project_billing`,
`billable_overrides` and `billing_budgets`, which the SPA reads as
optional and names only when they are not zero.

A 1.3 file imported into an API older than 1.3 loses its budgets
silently, since `_Backup` does not forbid keys it does not know; a 1.2
file has the same gap against a 1.1 API. This is accepted, and DATA.md
says so.

A contract refusal still comes partway through the projects, as before
1.2 (DATA.md, *Export*): the clients and the projects before it stay
written, and nothing after it is. Fixing the conflict and importing again
is safe.

---

## The UI's rules

- **The Clients page** (`/clients`) leads with a sentence of the API's
  figures (`pages/clients/summary.ts`): "€3,527.50 billable so far in
  October, across 2 clients.", several currencies listed and never added,
  then what the amount leaves out — hours on client projects not billed,
  hours with no rate yet, a timer still running. Then one panel per client:
  the rate in force today, the month's figure, the lines as a table, and
  the entries, each with its Billable pill, which always reads "Billable"
  and draws which way it is set: a check and the holiday tint on, struck
  through off, so its name is the words on it whichever way. Freelance
  hours billed to no one get a panel of their own, each with *Bill it*,
  before the first client too. The month is the URL's
  `?month=`, stepped with ‹ ›; next stops at the current month.
- **The nav offers Clients** once there is a client, archived or not, or a
  freelance project. Before that the page would only say "add a client",
  and most people never bill anyone.
- **The SPA never prices anything.** Every hour and amount on screen is the
  API's. The one rule it runs itself is the flag, `entryBillable` with
  `inForceOn` (`entities/billing/model/resolve.ts`), so a Billable pill
  shows what the report counts on any day and changes at once when tapped.
  It is a rule implemented twice, so it has parity tests against the
  Python cases.
- **Money in and out** (`shared/lib/money.ts`): `formatMoney` shows minor
  units in the API's `minor_units`; `parseMoney` reads the text, never
  `parseFloat`: one `.` or `,` as the separator, at most `minor_units`
  digits after it — more are refused, never rounded — and no thousands
  separators, signs, zero, or more than the API's maximum. A `,` before
  exactly three digits is refused in every currency: "25,000" is twenty-five
  thousand to one reader and 25.000 to another, and with three decimals
  (IQD, KWD) both parse.
- **Consent** is `withPastConsent`: a write goes with `rewrite_past` false;
  on `RETROACTIVE_CHANGE` the user is asked in the API's own words, and the
  write is sent again with it true only if they agree.
- **Dates are picked, never filled in.** A client's rate row takes its day
  from a chip (1st of this month, today, 1st of next month) or the
  calendar. Bill this project's "Billable from" starts on the project's
  first tracked day, "All of its time so far", or today when there is none,
  and the user sees it and can move it.
- **Every billing or client write** refreshes the billing reads and the
  clients (whose `currency_locked` it can move), and every session write,
  timer start and timer stop refreshes the billing reads, through root keys in
  `shared/api/keys.ts`, so no entity imports another.
- **When the routes cannot be reached** — an older API during a deploy —
  the Clients page and the project page's Billing panel say "Billing isn't
  available right now", and nothing else is affected. Ship the API first;
  one PR is safe either way.

---

## The coach, devices and privacy

- **The coach** gets no billing port, and `coach/` does not change. It
  sends a project's name as before, which may be a client's name if the
  project was named so. Sending any of the billing data to it would start
  with a change to PRIVACY.md, as `coach/contract_section.py` does for a
  contract's figures.
- **Devices** are kept off by the choice of prefixes, the comment in
  `server.py`, and one HTTP test: a device token gets 403 on
  `/api/clients/`, `/api/billing/month`, `/api/billing/entries/{id}`,
  `GET /api/billing/budgets` and `PUT /api/billing/budgets/clients/{id}`.
- **Webhooks** are unchanged; there are no billing events, and no budget
  events: `timer.start` and `timer.stop` carry what they always did.
- **A contact's name and email** belong to a third party. They are shown,
  never mailed or sent anywhere, and they are in the export and in an
  account's deletion (PRIVACY.md).

---

## Billing budgets (phase 1b)

> A freelancer sets a limit on a client, or on one billed project, in hours
> or in money, and Beats says how much of it is spent, how much is left, and
> when it is about to run out: including while a timer is running on it now.

A **billing budget** is a limit over figures 1a already works out. The only
thing stored is the limit. What has been spent, what is left, the warnings
and the projection are worked out again on every read, and none of them is
stored, sent anywhere or acknowledged. Following Decision 15, the code
always says *billing budget* (`BillingBudget`, `billing_budgets`,
`BILLING_BUDGET_…`, `useBillingBudgets`), never "budget" alone, because
`WeeklyPlan.budgets` and the coach's `BudgetExceeded` / `BUDGET_EXCEEDED`
already use the word. The UI says "budget": on the Clients page and in the
Billing panel nothing else could be meant.

The decisions below were made in the design of AHM-95. They build on 1a's
decisions 1–15 above and change none of them; "decision N" in this section
means one of its own.

### Decisions

1. **One billing budget per scope, and the scope is a client or a billed
   project.** It is addressed by its scope
   (`/api/billing/budgets/clients/{id}`, `/api/billing/budgets/projects/{id}`),
   the way a project's billing is addressed by its project, so it has no id
   of its own. A client's budget counts every project billed to it,
   archived ones included; a project's counts that project only. Both can
   exist at once and each is read on its own: neither rolls up into the
   other, and nothing is said about nesting. The common pair, a monthly
   retainer on the client and a fixed quote on one of its projects, takes
   two scopes, never two budgets on one.
2. **A project budget needs a billed project**: the caller's (404), with a
   `project_billing` (409 `BILLING_BUDGET_NEEDS_BILLING`, "Bill this project
   to a client before giving it a budget"). That is 1a's Decision 3 again,
   no dormant money on a project that cannot read it. `ProjectNotBilled`
   (404, no code) stays as it is on `DELETE /api/billing/projects/{id}`; the
   new code is named for budgets so the two cannot be confused.
3. **What counts is billable hours only, exactly 1a's lines.** An hours
   budget counts the scope's `billable_hours`, priced or not; a money budget
   its `amount_minor`. Overrides, dated terms, the rate in force each day
   and rounding once per line all apply unchanged, because the figures come
   from `assemble_client`. Hours that are not billable never spend a budget:
   a budget is what the client pays for. A budget stored without a future
   "what counts" field reads as billable, which is what every 1b budget
   means.
4. **Unit: hours or money, and money is the client's currency.** A money
   budget is an integer number of minor units in the currency of the
   scope's client, which for a project is the client its billing names. No
   currency is stored on the budget. Two rules keep the client's currency
   fixed for as long as a money budget depends on it:
   - **The lock.** A money budget on the client, or on any project billed to
     it, locks the client's currency: `_locked` counts it, `currency_locked`
     turns true, and a currency change is 409 `CURRENCY_IN_USE`, "This
     client's rates or billing budgets are in its currency; its currency can
     no longer change".
   - **The move.** A project with a money budget cannot move to a client in
     another currency: 409 `CURRENCY_MISMATCH`, raised as
     `BillingBudgetCurrencyMismatch` with its own message, "This project's
     billing budget is in EUR; remove it before moving the project to a
     client in another currency". `_check_move` checks it before 1a's terms
     and marks, so the refusal names the real reason. An hours budget moves
     with its project unconditionally, and so does a money budget between
     two clients in the same currency.
5. **A money budget is allowed while some hours have no rate.** Refusing it
   would block whoever sets the budget before the rate. What is spent is
   the priced amount only; the unpriced hours are reported beside it as
   `unpriced_hours`, never counted as zero and never guessed. The state is
   judged on the priced amount, the row says what that leaves out, and a
   money budget with unpriced hours in its period gets no projection: it
   would forecast a figure known to be short.
6. **Two periods, `monthly` and `total`.** A monthly budget is the calendar
   month, every month, and takes no dates (`starts_on` must be null). A
   total is one cap from `starts_on` (required) on, with no end: a
   fixed-price job is a total on its project, started the day the work
   started, and it ends when the project is archived or the budget removed.
   There is no end date and no fixed range. A total whose `starts_on` is
   after today is *upcoming*: no figures yet, and the row says "Starts Nov 1:
   120 h in total."
7. **Spend is a sum of whole calendar months, each worked out as the month
   report works it out.** A beat belongs whole to the local day it started
   on, in the read's required `tz`.
   - A monthly budget's spend is `assemble_client` over the 1st through
     today: exactly the Clients page's figure.
   - A total's is the sum, over every calendar month from `starts_on`
     through today, of `assemble_client` over that month's days; the first
     month is clipped to `starts_on` and the current one runs to today.
   - **Why months and not one range.** `_lines` makes runs of consecutive
     days within the range it is given. Over one long range a run at one
     rate across a month boundary would be rounded once, where the invoices
     rounded it once a month. 1 h 0 m 18 s at 85.00 EUR/h on each of 31
     October and 1 November is 1.01 h + 1.01 h = 2.02 h, €171.70, month by
     month; as one range it would be 2.01 h, €170.85. Budgets use 2.02 h, so
     a total agrees with the months invoiced to the minor unit. Do not
     "fix" it into one range.
   - A total's first month counts from `starts_on`, so it may differ from
     that month's invoice by what was worked before the day, which is the
     point of choosing it.
8. **Only the current period is read.** The limit is not dated: editing a
   monthly limit changes this month's reading, and a past month would be
   read against a limit set later. A budget reads as of today in `tz`, and
   a past month on the Clients page shows none. The history of what was
   spent is the month report.
9. **Two thresholds: a warning the caller sets, and 100 %.**
   `warn_at_percent` is a required strict integer from 1 to 99, which the
   dialog pre-fills with 80; there is no API default. The second threshold
   is always 100 %. The states are `under`, `near` (`spent × 100 ≥ warn ×
   limit`) and `used_up` (`spent ≥ limit`); going over is a negative
   remaining ("2 h over"), not a fourth state. Every comparison is in
   integers, hours as hundredths and money as minor units: with 40 h and a
   warning at 80, 31.99 h is under, 32.00 h near and 40.00 h used up; with
   333 minor units, 266 is under and 267 near. `percent_used` is rounded
   down and not capped, so 39.84 of 40 h reads 99 % and 100 % never shows
   before the budget is used up.
10. **A running timer is answered with instants, not a moving figure.**
    - 1a's Decision 9 holds: `spent`, `remaining`, `state` and the
      projection never include a running beat, so a budget agrees with the
      Clients page line for line, and two reads with no edit between them
      agree.
    - When a running beat counts on the scope, the reading adds `running`:
      `project_id`, `since`, `priced`, and two UTC instants, `near_at` and
      `over_at`, at which this beat alone would cross the warning and the
      limit. For hours that is `since + (threshold − spent) h`; for money
      `since + (threshold − spent_minor) ÷ rate_minor h`, at the rate
      `resolve_entry` gives on the beat's local start day, which holds for
      the whole beat. Each is rounded up to the whole second.
    - An instant is null for a threshold already crossed, and both are null
      when the beat has no rate under a money budget. They are worked out
      from stored data in UTC, so a DST change is just elapsed time and
      they do not move between reads.
    - A running beat counts when it is on a project in the scope, it would
      be billable (its override, else its start day's term), and its local
      start day falls in the current period. A timer started at 23:00 on 31
      October is October's, and leaves November's monthly reading at
      midnight: the start-day rule, documented rather than special-cased.
    - More than one counts only through `POST /api/beats/` or a restore;
      then `running` names the earliest and both instants are null.
    - A stopped beat joins a line and is rounded with it, so the real
      crossing can sit up to 18 s (0.005 h), or a minor unit, from the
      instant. The copy says "around" and shows minutes.
    - The SPA only compares the clock with an instant it was sent; it never
      adds hours or prices anything. The same comparison lifts the state it
      draws, from under to near or to used up, once an instant has passed.
11. **"About to run out" is the remaining amount and a guarded projection.**
    `remaining` is the limit less what is spent, in the unit, negative when
    over. `runs_out_on` is `today + ⌈remaining ÷ (window spend ÷ window
    days)⌉`, the window being the last `min(28, days elapsed in the
    period)` days, today included, its spend summed month by month as in
    decision 7. It is null when fewer than 7 days of the period have passed
    (a monthly budget first projects on the 7th), when nothing was spent in
    the window, once used up, while a money budget has unpriced hours in its
    period, while upcoming, when the day falls after the month's last (a
    monthly budget that lasts the month says nothing more), or when it is
    more than 365 days away. The pace is per calendar day, weekends
    included: crude but explainable, so the copy says "around". A running
    beat is not part of the pace; its effect is the instants.
12. **Alerts are derived on every read and stored nowhere.** Nothing is
    sent, acknowledged, snoozed or marked "sent once"; a used-up budget
    stays used up until the period rolls, the limit is raised or the budget
    is removed. They appear on the budget rows of the client's panel and the
    project's Billing panel, as one note per near or used-up budget in the
    Clients page's sentence (current month only), and as a dot on the
    Clients nav item **only while some active budget is used up**, a passed
    `over_at` counted. A "near" dot lit for ten days would teach people to
    ignore it, and the notes cover "near". There is no webhook event (the
    `timer.start` and `timer.stop` payloads are unchanged), nothing in the
    coach, nothing on a device, and no email or push.
13. **An archived scope's budget is kept, read, and never alerts.** A budget
    on an archived client, on an archived project, or on a project whose
    client is archived is still worked out and shown wherever its panel is,
    with `active: false`; it adds no note and lights no dot, and
    unarchiving brings its alerts back. The API accepts a write on an
    archived client, as 1a bills one, since a restore may carry it; the UI
    does not offer it. An archived project billed to an active client still
    counts toward that client's budget: it is billed.
14. **A budget is never lost as a side effect without being named.**
    - `DELETE /api/billing/projects/{id}` takes a required
      `remove_billing_budget`, as it takes `rewrite_past`. While the project
      has a budget and the key is false, the answer is 409
      `PROJECT_HAS_BILLING_BUDGET` ("Website has a billing budget; stop
      billing it with its budget, or remove the budget first"). With it
      true, the budget and the billing go in one service call. The checks
      run in this order: not billed (404), the budget, then the retroactive
      gate, so a declined `RETROACTIVE_CHANGE` leaves both records in place.
      The budget is deleted before the billing: a failure between the two
      writes leaves a billed project without its budget, which can be
      redone, never a budget on an unbilled project.
    - The SPA sends `true` only from a confirmation that names the budget:
      "Stop billing Website? Its terms and its budget go; its hours stay." A
      tab that never saw the budget sends false and shows the API's
      sentence.
    - Deleting a client is possible only while nothing is billed to it, so
      its budget counts nothing; the delete takes the budget with it, budget
      first and client second, with no refusal.
    - A project is never deleted (the projects router has no DELETE), and a
      billed project's kind cannot change (`PROJECT_HAS_BILLING`), so
      neither can strand a budget.
    - A budget whose scope has gone, which only a crash between two writes
      could leave, is skipped on read and left out of the export, as 1a
      skips a billing whose project is gone. A project budget counts as
      gone once its project is no longer billed.
15. **No retroactive gate on budget writes.** A budget changes no billable
    figure: lines, amounts, the month report and invoices never read one,
    and only the current period is shown. Budget writes take neither `tz`
    nor `rewrite_past`. 1a's gated writes (rates, terms, moves) still move a
    budget's spend, since it is derived from them, and keep their gate.
16. **The privacy wall extends, with nothing moved.** A collection of its
    own scoped by `user_id`, the `/api/billing` prefix no device token
    reaches, and no coach port. When phase 4 brings the money permission,
    `unit` is what lets it hide money budgets while still showing hours
    budgets, if it chooses to.

### Data model

`billing_budgets`, one document per scope, user-scoped through
`MongoStore` and stored in JSON form, as 1a's collections are. The models
are in `domain/models.py`, beside `ProjectBilling`.

```python
BILLING_BUDGET_HOURS_MAX = Decimal("100000")  # a lifetime cap, in hours
BILLING_BUDGET_MINOR_MAX = 1_000_000_000_000   # 10,000,000,000.00 at two decimals; far inside 2**53

class BillingBudgetScope(StrEnum):  CLIENT = "client"; PROJECT = "project"
class BillingBudgetUnit(StrEnum):   HOURS = "hours";   MONEY = "money"
class BillingBudgetPeriod(StrEnum): MONTHLY = "monthly"; TOTAL = "total"

class BillingBudgetFields:      # the PUT body: every key required, null where it may be
    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: Decimal | None  # hours only: > 0, <= max, at most 2 decimal places
    limit_minor: int | None      # money only: strict, > 0, <= max, in the client's currency
    starts_on: date | None       # a total: required; monthly: null
    warn_at_percent: int         # strict, 1..99; 100 % is always the second threshold

class BillingBudget(BillingBudgetFields):  # collection `billing_budgets`, one per scope
    scope: BillingBudgetScope
    scope_id: str                # a client's id or a project's
```

- **The shape rules are field validators** (`a_limit_in_hours_only_in_hours`,
  `a_limit_in_money_only_in_money`, `a_start_only_on_a_total`), so a 422's
  `fields` names the key: exactly the limit that matches `unit` is set, and
  `starts_on` follows the period. They read `unit` and `period` with
  `info.data.get`, so when one of those failed, its own error is the
  answer. `limit_hours` arrives as a JSON number and is held as `Decimal`
  (37.333 and `true` are 422s); the SPA sends it from integer hundredths,
  never through `parseFloat`, and it goes out as a float, as every hour
  figure of 1a does. `BillingBudget` restores the defaults for a stored
  `None`, as `Client` does, with the same field rules.
- **The rules that read other records are checked in the service**, for
  1a's reason: the scope exists and is the caller's, a project scope is
  billed, the lock and the move.
- **Index**: `billing_budgets (user_id, scope, scope_id)`, unique, so a
  second PUT on a scope replaces the first. Every other read lists the
  whole collection, a small set.
- **The port** `BillingBudgetStore` (`domain/ports.py`) has `list_all`,
  `get(scope, scope_id)`, `upsert` and `delete(scope, scope_id) -> bool`.
  `MongoBillingBudgetRepository` inherits the `BillingBudgetRepository`
  Protocol. Only `BillingService` is given it, and the full export reads it
  (`BillingBudgetRepoDep`): `CoachRepos` and every service a device reaches
  get nothing.

### The arithmetic

Pure, in `domain/billing_budgets.py`, made of `domain/billing.py`: it reads
no clock, and the day a budget is read on arrives as `today`.
`assemble_client` and `ClientBilling` are 1a's, unchanged; the running beat
is resolved here, with 1a's own `resolve_entry`.

- `billing_budget_days(budget, today)`: the period's `first` and `last`
  (a month's end, or none on a total), `through` (today, or none while
  upcoming) and `upcoming`.
- `month_slices(first, last)` cuts a span of days at each 1st of a month.
- `scope_spend(client, billings, projects, beats, overrides, first,
  through, tz)` sums `assemble_client` over each slice: `billable_hours`,
  `unpriced_hours` and `amount_minor`. `billings` is already narrowed to the
  scope. The beats are sorted into local months once and each month gets
  only its own; `assemble_client` checks each beat's day again, so the
  bucketing rule stays in one place.
- `billing_budget_state(limit, spent, warn)` and `percent_used(limit,
  spent)` compare integers.
- `running_crossings(...)` finds the running beat or beats that count and
  works out `near_at` and `over_at` (decision 10).
- `runs_out_on(window_spend, window_days, remaining, today, period_last,
  days_elapsed, incomplete)` applies the guards of decision 11.
- `billing_budget_status(...)` puts them together into one
  `BillingBudgetStatus`.

### The service

`BillingService` takes a `budgets: BillingBudgetStore`.

- **`billing_budget_statuses(tz)`** reads the budgets first and, with none,
  nothing else, so the nav dot's read costs nothing for someone who never
  set one. Otherwise it reads the clients, the billings and the projects
  (archived ones too) once each; the beats of every project in any scope
  once, from local midnight on the earliest period's first day to local
  midnight after today, running ones included (no beats at all while every
  budget is upcoming); their overrides once; and the clock once. It skips a
  budget whose client, project or billing has gone, and leaves out of a
  client's scope a billing whose project has gone, as `period` does. It
  orders the result by client name: the client's own budget first, then its
  projects' by project name.
- **`set_billing_budget(scope, scope_id, fields)`**: the 404s (the client's
  `CLIENT_NOT_FOUND`, or the project's), then 409
  `BILLING_BUDGET_NEEDS_BILLING`, then the upsert. An archived client is
  allowed. It returns the budget with its scope's client, for the
  response's currency.
- **`remove_billing_budget(scope, scope_id)`** is idempotent.
- **1a's methods**: `_locked(client, billings, budgets)` counts money
  budgets for `list_clients`, `update_client` and `_record`;
  `_check_move(..., money_billing_budget=)`; `remove_project_billing(...,
  remove_billing_budget=)`; `delete_client` deletes the client's budget;
  `check_restore` takes the file's budgets; `restore_billing_budget(budget)`
  is an ungated upsert.

### HTTP contract

The routes are in the `/api/billing` table above. Someone else's client or
project, or a malformed id, is 404, never 403, and every error uses the
unified envelope.

```jsonc
// GET /api/billing/budgets?tz=Europe/Berlin   (2026-10-18, 13:05 local; a timer on Website since 09:10)
[{ "scope": "client", "scope_id": "66e…", "client_id": "66e…", "name": "Studio Kite",
   "active": true, "currency": "EUR", "minor_units": 2,
   "unit": "hours", "period": "monthly", "limit_hours": 40.0, "limit_minor": null,
   "starts_on": null, "warn_at_percent": 80,
   "upcoming": false, "first": "2026-10-01", "last": "2026-10-31", "through": "2026-10-18",
   "billable_hours": 35.5, "unpriced_hours": 0.0, "amount_minor": 301750,
   "remaining_hours": 4.5, "remaining_minor": null,
   "percent_used": 88, "state": "near", "runs_out_on": "2026-10-21",
   "running": { "project_id": "66f…", "since": "2026-10-18T07:10:00Z", "priced": true,
                "near_at": null, "over_at": "2026-10-18T11:40:00Z" } },
 { "scope": "project", "scope_id": "66f…", "client_id": "66e…", "name": "Website",
   "active": true, "currency": "EUR", "minor_units": 2,
   "unit": "money", "period": "total", "limit_hours": null, "limit_minor": 1020000,
   "starts_on": "2026-09-01", "warn_at_percent": 80,
   "upcoming": false, "first": "2026-09-01", "last": null, "through": "2026-10-18",
   "billable_hours": 84.0, "unpriced_hours": 3.5, "amount_minor": 684250,
   "remaining_hours": null, "remaining_minor": 335750,
   "percent_used": 67, "state": "under", "runs_out_on": null,
   "running": { "project_id": "66f…", "since": "2026-10-18T07:10:00Z", "priced": true,
                "near_at": "2026-10-18T22:40:00Z", "over_at": "2026-10-19T22:40:00Z" } }]
```

- Hours are worked in `Decimal` and declared `float` only in the response
  schemas. Money is integer minor units, always with `currency` and
  `minor_units` beside it.
- `billable_hours`, `unpriced_hours` and `amount_minor` are always present,
  whatever the unit; only the budget's own unit has a `remaining_…`, the
  other is null.
- An upcoming total has `through` null, zero figures, `state` "under", and
  no projection or running block.
- A PUT answers with the stored budget and `client_id`, `currency` and
  `minor_units` beside it, not the reading: the SPA refreshes the billing
  root and reads the list again.
- Routes that gain behaviour, with their shapes unchanged but for the one
  new key: `DELETE /api/billing/projects/{id}` (`remove_billing_budget`,
  decision 14); `PUT /api/billing/projects/{id}` (the move, decision 4);
  `PUT /api/clients/{id}` and every `ClientResponse`'s `currency_locked`
  (the lock); `DELETE /api/clients/{id}` (takes the budget); the backup
  (1.3). `/api/billing/month`, `/api/projects`, `/api/beats`, `/api/timer`,
  `/api/device`, the webhooks, the coach and the daemon's routes keep their
  shapes byte for byte.

The trade-off of a required `remove_billing_budget` is deploy skew: an SPA
tab opened before the API deploy gets a 422 naming the key on Stop billing
until it is reloaded. Making the key optional and false by default would
also be safe, since it only ever refuses; it is required to match
`rewrite_past` on the same route.

### The UI's rules

- **Every hour and amount on screen is the API's.** The SPA's own logic is
  the clock comparison of decision 10 (`billingBudgetState(status, now)`)
  and putting the API's figures into words (`describeBillingBudget(status,
  now)`, which gives `{ sentence, unpriced?, running?, note? }`): both pure,
  in `entities/billing/model/budget.ts`. One row component,
  `BillingBudgetRow`, draws the sentence (its figures in `font-mono`), the
  meter, the unpriced note and the running line on both pages.
- **The data.** `useBillingBudgets(tz, { enabled })` sits under the billing
  root, so every session write, mark, term, rate and timer stop refreshes
  it, with `staleTime` 0 as the month and no refetch interval: the instants
  are stable, and `useNow` (`shared/lib`), a minute's tick mounted only
  while some reading has `running`, re-renders the sentences and the state.
  The timer refreshes the billing root on start as on stop, and whenever
  the polled status's `since` changes, so a timer started or stopped from
  the companion, the daemon or the wall clock reaches the budgets within
  one status poll; `useTimer` is mounted in `app/Layout.tsx`, so this holds
  on every page.
- **The Clients page, current month only.** The client's panel has a
  **Budget** block under the month's figure: the client's own row, then a
  row per project budget, each with a pencil that opens the dialog for that
  scope. With no budget at all, the panel shows a quiet *Set a budget* link
  and nothing else; with project budgets but none of the client's own, the
  block ends with *Set a budget for Studio Kite*. A project row's unpriced
  note links *Set its rate* to the project. `describeMonth` adds one note
  per active budget that is near or used up, after 1a's notes. A past month
  reads no budget.
- **The project's Billing panel** (a billed project only), under "This
  month: …": the project's budget row, with edit and remove, or *+ Set a
  budget*; then, when its client has a budget, a read-only line, "Also
  counts toward Studio Kite's budget: 4.5 h left this month → Clients". With
  a budget, *Stop billing* names it (decision 14).
- **`BillingBudgetDialog`**, one column, so it works at phone width as it
  is:
  - *Measure in*: *Hours* (preselected, since it works before any rate
    exists) or *Money (EUR)*, with the currency named by `Intl.DisplayNames`
    below ("In Euro, the client's currency."): shown, never chosen.
  - *Budget*: hours through `parseHours`, money through `parseMoney` at the
    API's `minor_units`, capped at `BILLING_BUDGET_MINOR_MAX`. Both run on
    `parseAmount` (`shared/lib/money.ts`): one `.` or `,`, no more decimals
    than allowed — refused, never rounded — and never `parseFloat`.
  - *Resets*: *Every month* (preselected on a client) or *In total*
    (preselected on a project).
  - *From*, on a total, picked and never typed: *When billing started (Sep
    1)*, the earliest term of the scope's billing (for a client, across its
    billed projects), preselected; *1st of this month*; *Today*; or the
    calendar. With no term to start from, *1st of this month* is
    preselected.
  - *Warn me at*: 80, pre-filled, "% — and again when it's used up".
  - *Save*, and *Remove budget* when there is one.
  - Every key is sent, the other unit's limit null and a monthly budget's
    `starts_on` null. A 422's `fields` lands on its input; a 409 shows in
    the API's words.
- **The copy**: plain sentences, the sentence before the number,
  `hoursText` (`shared/lib/format.ts`) and `formatMoney`.

  | State | Sentence |
  |---|---|
  | Under | "18 h of 40 h this month · 22 h left." |
  | With a projection | "34 h of 40 h this month · 6 h left. At this pace it runs out around Oct 24." |
  | Used up | "40 h of 40 h this month: used up." |
  | Over | "43.5 h of 40 h this month: 3.5 h over." |
  | Total | "€6,842.50 of €10,200.00 since Sep 1 · €3,357.50 left." (a start in another year adds it: "since Sep 1, 2025") |
  | Unpriced hours, money budget | "Plus 3.5 h with no rate yet." in 1a's no-rate tint, with *Set its rate* on a project's row on the Clients page |
  | Upcoming | "Starts Nov 1: 120 h in total." |
  | Running | "A timer is running: it uses the last 4.5 h around 13:40." Once past: "The running timer used it up around 13:40." |
  | Running, no instant (two timers, or used up already) | "A timer is running; it counts once stopped." |
  | Running, unpriced, money budget | "A timer is running on hours with no rate; they count once a rate is set." |
  | Note, near | "Studio Kite's budget for October is 88% used: 4.5 h left." (a total has no "for October") |
  | Note, near with a running crossing | "Studio Kite's budget runs out around 13:40 if the timer keeps going." |
  | Note, used up | "Website's budget is used up: 2 h over.", or "… is used up." at the limit |
  | Note, used up by the running timer | "Studio Kite's budget was used up around 13:40 by the running timer." |

- **The meter** (`BillingBudgetMeter`) has `role="meter"`, `aria-valuenow`
  at `percent_used` held to 0–100, `aria-valuetext` "88% used", and a tick
  at `warn_at_percent`. A native `<meter>` would draw its own bar, which
  takes neither the tick nor the theme's fills. The fill is the sun
  (`accent`) while under, the persimmon `destructive` fill once near, and
  `destructive-ink`, at full width, once used up. 1a's no-rate tint was
  not used for near: its ink is too close to `destructive-ink` to tell
  near from used up. The sentence always sits beside it, so colour is never
  the only signal.
- **The nav dot** comes from `useBillingBudgetAttention(showClients)` in
  `widgets/sidebar`: it reads the budgets only when the nav offers Clients,
  and lights only for an active budget that is used up, a passed `over_at`
  counted. In the sidebar and on the Clients item of the mobile drawer, the
  item's accessible name becomes "Clients, a billing budget is used up". No
  dot when the read fails.
- **When the read fails**, an older API during a deploy, each budget block
  says "Budgets aren't available right now." and everything else, 1a's
  panels included, renders as before: no notes, no dot. Ship the API first.
- **At phone width** the sentence comes first and the meter runs full
  width below it; the dialog's chips wrap. There is no new table, so
  nothing scrolls sideways. The Playwright check in `e2e/clients.spec.ts`
  holds both pages to that at 1280 px and 390 px.

### Left out of 1b

Each addable later without migrating data:

- **Pushed alerts**: webhook events for thresholds (they need "sent once"
  state, and phase 4's permission before money reaches a third party);
  email, web push and OS notifications; anything on the companion, the menu
  bar, the daemon, the editor extension or the wall clock.
- **The coach**: any budget figure in a brief or a chat, which would start
  with a change to PRIVACY.md.
- **Stored alert state**: acknowledging, snoozing or dismissing an alert,
  and an alert history.
- **In-app toasts and the sidebar timer**: a toast at a crossing instant, a
  budget line beside the running timer.
- **Stopping at the limit**: blocking, or confirming, a timer start on a
  used-up budget.
- **More thresholds**, and **several budgets per scope** (a monthly and a
  total cap on one project).
- **Dates**: an end date on a total, fixed ranges, an "ended" state.
- **Dated limits and history**: a budget read against past months. A stored
  single limit can later read as one term from the start.
- **Other periods**: weekly or quarterly, and rolling unused retainer hours
  over to the next month.
- **What counts**: non-billable hours, or all hours, on a scope.
- **Where budgets can go**: unbilled freelance projects, side projects, day
  jobs (they have the contract balance), tags, spans of several clients.
- **Currency**: budgets in another currency, exchange rates, tax, overage
  pricing.
- **A smarter projection**: pace from working days, the calendar, plans or
  contracts.
- **The dialog's anchor**: last month's figure for the scope beside the
  limit.
- **Other places**: 1c's report links, the sessions CSV, invoices, the
  Insights and Plan pages, and any link to `WeeklyPlan` targets or
  `weekly_goal`.
- **Organisations**: organisation-owned budgets and the money permission
  (phases 2 and 4).

---

## Report links (phase 1c)

> A freelancer sends a client a link. The client opens it in any browser,
> with no login and no account, and sees the hours on their own projects for
> a range the freelancer fixed — and, if the freelancer chose, what they
> cost. Nothing else about the freelancer is reachable from it.

This is the first time any Beats data reaches a reader with no session, which
makes it the place to be strict rather than clever. A link holds no figures:
it names a client, a range and a timezone, and every number is worked out on
each read by the 1a arithmetic, through `assemble_client`.

The decisions below are 1c's own. They build on 1a's decisions 1–15 and 1b's
and change none of them; "decision N" in this section means one of its own.

### Decisions

1. **A link is a capability in its URL**, 32 bytes from
   `secrets.token_urlsafe`, and it is stored as it is read, not hashed. A
   pairing code is hashed because it is eight guessable characters that live
   for minutes; this is neither. Hashing would protect nothing here — whoever
   can read the `report_links` collection can read the hours it serves, out of
   the same database — and it would cost the one thing the owner needs, which
   is to open the link they sent a client last month and see what the client
   sees. The token is the whole secret, so it is never put in a log line, and
   the route it sits on is rate-limited (decision 8).
2. **The range and the timezone are frozen when the link is minted.** A link
   stores `first`, `last` and the owner's `tz`, and its figures never move
   again: the days are bucketed in the owner's zone, not the reader's, because
   those are the days the owner invoiced on, and a client in Auckland reading
   a Berlin freelancer's October must see October as it was billed. With a
   fixed range and 1a's decision 9 — a running beat is not billed — two reads
   of one link a week apart agree, unless the owner edited the underlying
   time. The range is capped at 366 days: a report link backs an invoice
   period, and the assembler walks the range day by day.
3. **A link names one client, and the read never fetches another's.**
   `BillingService.client_period` reads that client's billings, those
   billings' projects, those projects' beats in the range, and those beats'
   overrides — then calls `assemble_client`. It never calls `period`, which
   assembles every client and would leave the public route filtering a list it
   should never have been handed. A reader of one client cannot reach
   another's because the query for another's was never made. This is the same
   reasoning as 1a's decision 2: a collection boundary, not a serialiser
   someone has to remember.
4. **The public response is its own schema, written field by field.**
   `ReportResponse` and its rows are not `ClientBillingResponse` with keys
   removed, and do not inherit from it. A field added to the private month
   report later — a note, a tag, a flow score — cannot reach a client's eyes
   by inheritance. The two schemas drifting apart is the point of them.
5. **What no link can show**, structurally, because it is not among
   `assemble_client`'s inputs: another client, a personal project, a day job,
   a side project, an unbilled freelance project, a tag, a flow score, a
   biometric, a calendar event, the coach, the account's name or email. What a
   link deliberately leaves out of what it *could* show: `client_id`,
   `project_id` and `beat_id` (a client has no use for the owner's internal
   ids), `non_billable_hours` (hours the client is not billed for are the
   freelancer's business), `overridden` (how a figure was arrived at is not
   the client's business either) and `running` (see decision 7).
6. **Notes do not cross in 1c.** The question *What the report lists* leaves
   open — whether a client's report shows an entry's note — stays open: a note
   is not threaded through `assemble_client`, so there is nothing to leak. It
   is a third flag whenever it is decided, defaulting off, and links already
   minted keep showing what their owner saw when they minted them.
7. **A link says nothing about now.** `running` is not in the response, so a
   client cannot learn from a report that a timer is on at this moment.
   AHM-74 makes live presence a per-member consent decision, off by default;
   a report link is not the back door to it.
8. **The public prefix is narrow, slow and uncached.** `/api/reports` is the
   only entry in `PUBLIC_PREFIXES` that serves a user's data, and it serves
   exactly one shape. The route is rate-limited to 30/minute, answers
   `Cache-Control: no-store` so a shared machine's browser keeps no copy, and
   `X-Robots-Tag: noindex` so a link pasted into something that crawls does
   not land in an index. A device token reaching it still gets 403: the
   middleware resolves a Bearer token and checks `device_may_reach` before a
   path's publicness is ever considered.
9. **One 404 for every way a link fails.** Not found, mistyped, revoked, or
   for a client that has since been deleted: all answer 404 `REPORT_NOT_FOUND`
   with the same words. A reader with no session must not learn from the
   difference between "never existed" and "revoked yesterday".
10. **Revoking is deleting.** `DELETE` removes the record and the URL is dead
    from the next read. A `revoked` flag beside a dead token would be a second
    state every read has to consider, for no gain: 32 bytes are never minted
    twice, so a deleted token cannot come back. Deleting a client takes its
    links with it, as it takes its billing budget.
11. **Minting is the owner's, under `/api/clients/{id}/links`.** Session token
    only, no device prefix, like every other billing route. The API returns
    the token, never a URL: the SPA knows its own origin and the API does not,
    and inventing a setting for it would be one more thing a self-host has to
    get right.
12. **Archived keeps reading.** A link on an archived client still serves, and
    an archived project with hours in the range is still a line. The owner
    archived them; the client still has an invoice to check.

### Data model

```python
REPORT_RANGE_MAX_DAYS = 366

class ReportLinkFields(BaseModel):  # the write body: every key required
    first: date_type
    last: date_type                 # not before `first`, at most 366 days
    tz: str                         # IANA; checked at write time, not here
    show_amounts: bool              # strict: rates, amounts and the currency
    show_entries: bool              # strict: the day-by-day rows under the lines

class ReportLink(ReportLinkFields):  # collection `report_links`
    id: str | None
    client_id: str
    token: str
    created_at: datetime
```

- **`last` and the cap are model validators**, since they are facts about the
  record that cannot start failing on a read. **`tz` is checked in the
  service**, with the same reasoning as the currency and the holiday region: a
  zone that leaves the tz database must not make a stored link unreadable.
- **Indexes** (`ensure_indexes`): `report_links (token)`, unique — the public
  lookup, which is the one read in the system that crosses users — and
  `report_links (user_id, client_id)` for the owner's list.
- **The repository is two classes**, as pairing codes are:
  `MongoReportLinkRepository` is user-scoped through `MongoStore` for the
  owner's list, create and delete, and reaches the service behind the narrow
  `ReportLinkStore` port, which has no way to resolve a token at all.
  `MongoReportLinkLookup` is unscoped and does nothing else, because the
  reader is not signed in and the owner is not known until the token
  resolves; it answers an `OwnedReportLink`, the link beside the account,
  since `user_id` is a column of every document and a field of no model.
  Resolving a token is the only place a request's account comes from anything
  but a token the caller proved, and the route says so at the call site.
- **The link is not in the backup.** `GET /api/export/full` stays at 1.3: a
  backup file that carried live URLs to a year of someone's hours is a worse
  thing to leave on a laptop than a lost link is to re-mint. A restore
  therefore brings back the clients and their billing, and no links.

### What a link shows

```jsonc
// GET /api/reports/{token}
{ "client_name": "Studio Kite",
  "first": "2026-10-01", "last": "2026-10-31",
  "show_amounts": true, "show_entries": true,
  "currency": "EUR", "minor_units": 2,     // null when amounts are hidden
  "billable_hours": 41.5,
  "unpriced_hours": 0.0,                   // null when amounts are hidden
  "amount_minor": 352750,                  // null when amounts are hidden
  "lines": [{ "project_name": "Website", "first": "2026-10-01",
              "last": "2026-10-14", "hours": 30.0,
              "rate_minor": 8500, "amount_minor": 255000 }],
  "entries": [{ "day": "2026-10-02", "start": "…Z", "end": "…Z",
                "hours": 2.5 }] }
```

- **Only billable work.** The lines are 1a's lines, which are billable by
  construction; the entries are filtered to the billable ones. A client sees
  what they are being asked to pay for and nothing beside it.
- **With `show_amounts` false**, `currency`, `minor_units`, `unpriced_hours`,
  `amount_minor` and every line's `rate_minor` and `amount_minor` are null.
  The hours still add up, so the link works as a proof of time with the price
  left out — which is what a client on a fixed fee should get.
- **With `show_entries` false**, `entries` is `[]`: the lines and the totals
  only. The flags are independent, so all four combinations are reachable.
- **Hours are the same figures the owner sees** on the Clients page for the
  same range, to the hundredth, because they come from the same assembler.

### HTTP contract

| Method | Path | Body, params | Answers |
|---|---|---|---|
| GET | `/api/clients/{id}/links` | | the client's links, newest first; 404 `CLIENT_NOT_FOUND` |
| POST | `/api/clients/{id}/links` | `ReportLinkFields` | 201 with the token; 404 `CLIENT_NOT_FOUND`; 400 `INVALID_TIMEZONE`; 422 |
| DELETE | `/api/clients/{id}/links/{link_id}` | | 204, always: with no such link there is nothing left to clear |
| GET | `/api/reports/{token}` | **public** | the report; 404 `REPORT_NOT_FOUND`; 429 |

### The UI's rules

- **The owner's side** is a *Shared reports* disclosure in `ClientPanel`,
  beside the budgets: the client's links, each with its range, its two flags
  in words, a Copy button and a Revoke button, and *Share October*, which
  reveals the two checkboxes and mints a link over the open month. It is
  closed until asked for and read only then (`enabled`), because the page
  draws a panel per client and an eager read would be one request per client
  for something most months nobody opens. Copy writes the SPA's own origin
  plus `/r/{token}`; an archived client still copies the links it has and
  makes no more.
- **The reader's side** is `/r/:token`, a route outside `ProtectedRoute` —
  beside `/auth/callback`, the only other public one — on its own page with no
  `Layout`, no sidebar and no nav: there is nothing for a reader to navigate
  to. It reads the public route with no bearer token, and a 404 is a plain
  "This report link is no longer available."
- **The SPA still prices nothing**: every hour and amount on the page is the
  API's, `formatMoney` with the API's `minor_units` as everywhere else.

### Left out of 1c

Each addable later without migrating data:

- **Notes** on an entry (decision 6), and tags, which 1a's decision keeps out.
- **An expiry date** on a link, and a password on one.
- **A label** the owner gives a link to tell two apart; the range does it today.
- **A read count**, a last-read time, or any record of who opened a link.
- **CSV or PDF** off the public page, and an invoice built from it.
- **A link scoped to one project** rather than a client, and one spanning
  several clients.
- **A rolling range** — "the last 30 days", "this month" — which decision 2
  rules out for now on purpose, since a moving figure is not something to
  invoice against.
- **Organisations**: a client that is an Acme organisation reads its hours
  through membership instead, and the link stays for clients who are not
  (stage 2, [organisations.md](organisations.md)). Stage 2 settled the notes
  question for both: an organisation reads an entry's note, a report link
  still does not.

---

## How later phases build on it

- **1b, billing budgets.** Built: see *Billing budgets (phase 1b)*. A
  budget is scoped to a client or a billed project, in hours or in money
  (minor units, in that client's currency), monthly or in total from a
  day, with a warning and 100 %. Its spend is the sum, month by month, of
  `assemble_client` over the scope, so a total agrees with the invoices to
  the minor unit; unpriced hours are reported as unpriced, never as zero. A
  money budget never mixes currencies, because a client has one.
- **1c, report links.** Built: see *Report links (phase 1c)*. A link names
  one client and a range, under a new public prefix, and is served by
  `assemble_client` with only that client's inputs, through a response
  schema written field by field; amounts only when the link says so. It
  cannot structurally reach other clients, personal projects, flow,
  biometrics or the coach, and since running beats are left out and the
  range is frozen, it shows the same figures on every read.
- **Stage 2, organisations.** Built: see [organisations.md](organisations.md).
  An organisation's project document carries `organisation_id` and no
  `user_id`; billing stayed personal and an organisation's project is billed
  by nobody (409 `ORGANISATION_PROJECT`), and the organisation's reads never
  touch these collections. `NOT_FREELANCE` can still loosen to "you are a
  contractor on it" without moving data.
- **Invoices.** An invoice is a frozen copy of a `period`'s lines, which
  per-line rounding lets it quote verbatim; an "invoiced through" date can
  replace the month boundary in `past_change`.
