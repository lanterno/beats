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
The rest says what was built on them and why. How the project page shows a
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
    (see *How later phases build on it*).
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
- **The currency is locked once priced** (Decision 12). `ClientResponse`
  carries `currency_locked` so the picker can say so before the user tries.
- **A client with billed projects** cannot be deleted (Decision 13).
- **A project's billing**: the project is the caller's (404) and freelance
  (409 `NOT_FREELANCE`); the client is the caller's (404
  `CLIENT_NOT_FOUND`), archived or not, since a restored backup may bill
  an archived client. A move to a client in another currency is refused
  (409 `CURRENCY_MISMATCH`) while the terms it would have there carry a
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
| DELETE | `/api/clients/{id}` | | 204; 409 `CLIENT_HAS_PROJECTS` |

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
| DELETE | `/api/billing/projects/{project_id}?tz=&rewrite_past=` | both required | 204; 404 when it is not billed; 409 `RETROACTIVE_CHANGE` |
| GET | `/api/billing/entries` | | every override, `{beat_id, billable}`: they are exceptions, so few |
| PUT | `/api/billing/entries/{beat_id}` | `{billable}`, strict | the override; 404 when the beat is not the caller's |
| DELETE | `/api/billing/entries/{beat_id}` | | 204, always: with no mark, or no beat, there is nothing left to clear |
| GET | `/api/billing/month?month=YYYY-MM&tz=` | both required | the month; 422; 409 `MONTH_NOT_STARTED` |

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

## Backup 1.2

`GET /api/export/full` is version `1.2`: beside the projects, sessions,
absences and adjustments it carries `clients` (archived ones too, ids
kept), `project_billing` and `billable_overrides`. The sessions CSV does
not change: its columns are a contract with spreadsheets, and billing has
its own report. Every list may be missing from a file, so a 1.0 or 1.1
backup imports as one with no billing.

The import checks the whole file before writing anything:

1. A record that does not parse is a 422, a client's id included (24
   hexadecimal digits, since it is kept).
2. A project, a session or a client whose id is another account's is 409
   `BACKUP_OF_ANOTHER_ACCOUNT`.
3. Each billing's project and client, and each override's session, must be
   in the file or the account; otherwise a 422 names the record
   (`project_billing.0.client_id`).
4. A dry run of the client and billing writes' rules over the file laid on
   the account (`BillingService.check_restore`): a currency the table does
   not know, on a client that is new or whose currency changes; a currency
   changed once priced (`CURRENCY_IN_USE`); billing on a project that is
   not freelance as the file leaves it (`NOT_FREELANCE`); a billed project
   the file moves away from freelance without billing it anew
   (`PROJECT_HAS_BILLING`); billing moved to a client in another currency
   (`CURRENCY_MISMATCH`), the file's sessions and billable marks laid on
   the account's for the marks it counts. The first refusal is the route's own error, its
   detail naming the record (`project_billing.0: Only a freelance project
   is billed`). The retroactive gate is not applied.

Then the writes, in this order: clients, kept ids and archive flags
included; projects, each an ordinary project write; each project's
billing; sessions; overrides; then absences and adjustments as before.
Billing is never added to `skipped`: its rules ran before the first write,
and the deployed toast counts every skip that is not an absence as a
balance adjustment, so a new kind of skip would mislabel it during a
deploy. `imported` gains `clients`, `project_billing` and
`billable_overrides`, which the SPA reads as optional and names only when
they are not zero.

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
  clients (whose `currency_locked` it can move), and every session write
  and timer stop refreshes the billing reads, through root keys in
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
  `/api/clients/`, `/api/billing/month` and `/api/billing/entries/{id}`.
- **Webhooks** are unchanged; there are no billing events.
- **A contact's name and email** belong to a third party. They are shown,
  never mailed or sent anywhere, and they are in the export and in an
  account's deletion (PRIVACY.md).

---

## How later phases build on it

- **1b, billing budgets.** A collection of budgets scoped to a client or a
  project, in hours or in money (minor units, in that client's currency),
  per month or over a range, with thresholds. Spend is
  `BillingService.period` filtered to the scope; unpriced hours are
  reported as unpriced, never as zero. A money budget never mixes
  currencies, because a client has one.
- **1c, report links.** A link names one client and a range, under a new
  public prefix, and is served by `assemble_client` with only that
  client's inputs, through an allowlist of what a client may see; amounts
  only when the link says so. It cannot structurally reach other clients,
  personal projects, flow, biometrics or the coach, and since running
  beats are left out it shows the same figures on every read.
- **Phase 2, organisations.** An organisation-owned project gains an owner
  on `Project`; a contractor's `project_billing` stays in their own
  collection, keyed by their `user_id` and the organisation's project id,
  and the organisation's reads never touch these collections.
  `NOT_FREELANCE` can loosen to "you are a contractor on it" without moving
  data.
- **Invoices.** An invoice is a frozen copy of a `period`'s lines, which
  per-line rounding lets it quote verbatim; an "invoiced through" date can
  replace the month boundary in `past_change`.
