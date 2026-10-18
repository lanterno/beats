# Data handling

The full inventory of what Beats stores, where it stores it, and how to get it back out. For a plain-English overview, see [PRIVACY.md](./PRIVACY.md).

## Where data lives

LifePete runs at **lifepete.com** on Google Cloud. Anyone can also run it
themselves with `compose.selfhost.yml`, and that copy keeps its own database. See
Infrastructure in [CLAUDE.md](./CLAUDE.md).

| Layer    | lifepete.com                                                               | Self-hosted (`compose.selfhost.yml`)                                     | What it holds                                        |
|----------|----------------------------------------------------------------------------|--------------------------------------------------------------------------|------------------------------------------------------|
| API      | Google Cloud Run                                                           | A container in the stack                                                 | Stateless — request handling only                    |
| Database | External MongoDB cluster, reached by the connection string Terraform takes | MongoDB container, `beats-mongo-data` volume, not published outside the stack | Every collection listed below                   |
| Web app  | Firebase Hosting                                                           | nginx in the same stack, one origin with the API                         | Static assets only                                   |
| Secrets  | GCP Secret Manager                                                         | `api/.env` and the environment on the host                               | OAuth client secrets, Anthropic API key, infra creds |
| Logs     | Google Cloud Logging                                                       | Container logs (`just logs`)                                             | Request logs (no request bodies)                     |
| Backups  | None configured in this repo                                               | `just backup <dir>`: a gzipped mongodump archive, taken on demand        | The database                                         |

## What's stored, by domain

### Account and auth

- User document: id, email, display name, created-at
- WebAuthn credentials: public key, credential id, sign counter, device label
- Refresh-token records for JWT rotation

No passwords are stored — Beats does not have a password login path.

### Work data

- **Projects**: name, description, colour, category, archive flag, GitHub repo, the local
  repo paths that auto-start the timer, the personal weekly goal (`weekly_goal`,
  `goal_type`, `goal_overrides`), and a `kind` — `day_job`, `freelance` or
  `side_project`. A day job may also carry a **contract**: `terms[]`, each with
  `effective_from`, `schedule_type`, `full_time_hours`, `percentage`, `weekly_hours` and
  a `note`; `holiday_country` and `holiday_subdivision` (ISO codes — the holidays are
  derived from them on request, no calendar is stored); `company_holidays[]`, the
  employer's own days off, each a `date` and the `name` you gave it;
  `holidays_not_given[]`, the dates of region holidays the employer does not give;
  `opening_balance_hours`; `ended_on`; and an optional `vacation` entitlement —
  `days_per_year`, `carry_over` (`all`, `capped`, `none`), `carry_over_max_days`,
  `opening_on` and `opening_days`, the days left on that date as you typed them. The
  vacation figures are derived from it and your absences on request; none is stored.
  On a day job whose contract governs the week,
  `weekly_goal` is cleared at startup: the contract is the goal.
- **Absences**: one document per day off on a day-job project — `user_id`, `project_id`,
  `date`, `half_day`, `type` (`vacation`, `sick`, `other`), `note`. Unique on
  `(user_id, project_id, date)`, so a second absence on a day replaces the first.
- **Balance adjustments**: one document per dated change to a day job's balance —
  `user_id`, `project_id`, `date`, `kind` (`delta`, `reset`, `cap`), `hours` (signed for a
  delta, the target for a reset or a cap), `note`. Unique on `(user_id, project_id, date)`,
  so a second adjustment on a day replaces the first. Deleted with the contract.
- **Clients**: one document per client you bill — `user_id`, `name`, `contact_name`,
  `contact_email`, `currency` (an ISO 4217 code), `rates[]`, each an `effective_from` and a
  `rate_minor` (the hourly rate in the currency's minor units: cents for EUR), `archived`
  and `created_at`. The contact's name and email address are a third party's: shown to
  you, sent nowhere. A client is deleted only while no project is billed to it, and its
  billing budget goes with it.
- **Project billing**: one document per billed freelance project — `user_id`,
  `project_id`, `client_id`, and `terms[]`, each an `effective_from`, `billable` and an
  optional `rate_minor` of the project's own. Unique on `(user_id, project_id)`, so a
  second billing on a project replaces the first. Kept apart from the project document,
  which paired devices read. A month's billable hours and amounts are derived from it,
  the client and the sessions on request; none is stored.
- **Billing budgets**: one document per client or billed project you set a limit on —
  `user_id`, `scope` (`client` or `project`), `scope_id`, `unit` (`hours` or `money`),
  `period` (`monthly` or `total`), `limit_hours` or `limit_minor` (the one its unit takes;
  money in the minor units of the client's currency, which is not stored again), a
  `starts_on` on a total, and `warn_at_percent`. Unique on `(user_id, scope, scope_id)`, so
  a second budget on a scope replaces the first. Only the limit is stored: what is spent,
  what is left, the warning and the projection are derived from it, the billing and the
  sessions on request, and no alert is stored or sent. Deleted with its project's billing
  when you stop billing it and say the budget goes too, or with its client.
- **Billable marks**: one document per session you marked billable or not, against its
  project's terms — `user_id`, `beat_id`, `billable`. Unique on `(user_id, beat_id)`.
  Deleted with the session.
- **Beats (sessions)**: start, end, project id, tags, a note.
  The tags are derived from the daemon's flow windows when a session is logged, stopped
  or its times are edited; an edit over no windows keeps the tags it had. The note comes
  only from an import. An edit writes the project, start and end it carries and the tags, a
  stop the end and the tags, and neither touches the note or anything else stored.
  Nothing records where a session came from (the timer, a manual entry, the daemon or the
  editor extension).
- **Timer state**: the currently-running beat per user
- **Plans**: weekly plans — a per-project hour target for a given week
- **Webhooks**: target URLs and which timer events they subscribe to. Deliveries
  are fire-and-forget; no delivery log is kept.

### Intelligence and coach

- **Signals**: flow windows and summaries emitted by the daemon
- **Focus scores**: per-session scores derived from sessions, computed on request and not stored
- **Inbox items**: surfaced patterns and suggestions
- **Weekly digests**: the generated summary of a week — hours, session count,
  top project, and the observation written alongside them
- **Coach memory**: long-running facts the coach has been told to remember
- **Coach chat history**: every prompt and reply, with timestamps

Coach prompts are sent to the [Anthropic Claude API](https://www.anthropic.com/) at the time of the request. Replies and the prompts that produced them are stored in the database.

### Integrations (only if you connect them)

- **Google Calendar**: OAuth tokens; cached event list per sync
- **GitHub**: OAuth tokens; cached commit/PR activity per sync
- **Fitbit**: OAuth tokens; cached daily biometrics
- **Oura**: personal-access token; cached daily biometrics
- **HealthKit / Health Connect**: biometrics pushed from the companion app (sleep, HRV, steps, etc.)

### Devices

- **Wall clock pairing**: device id, pairing token, last heartbeat, favorites, weekly bars

## Encryption

- **In transit**: on lifepete.com, HTTPS to the API and TLS to the MongoDB cluster. Self-hosted, the API reaches MongoDB over the stack's internal Docker network without TLS; the database is not published outside the stack.
- **At rest**: on lifepete.com, the MongoDB cluster's encryption at rest and GCP's for Secret Manager. Self-hosted, only what the host's disk provides: LifePete does not encrypt the Mongo volume or `api/.env`.
- **Application-level encryption**: Beats does not currently apply a second encryption layer to integration tokens beyond what MongoDB provides. If you need that, do not connect integrations.

## Retention

Beats does not auto-delete anything. Beats, notes, coach history, and biometrics persist until you delete them or delete your account.

## Export

`/api/export` returns the authenticated user's data. Nothing is held back behind a tier.

- **`/full`**, a JSON backup (version `1.3`), holds everything a day job's balance and a
  client's bill are made of: every project, archived ones too, with its contract; every
  session; every absence, including one kept from when its project was a day job; every
  balance adjustment; every client, archived ones too; every project's billing; every
  billable mark; every billing budget whose client, or billed project, is still there.
- **`/csv/sessions`** is a CSV of the completed sessions alone.

A day job with a contract also has a monthly timesheet,
`GET /api/projects/{id}/timesheet.csv?month=`, for handing to the employer. Per day it
holds the hours worked and expected, the balance adjustment's kind and what it moved,
the public holiday's name (a company holiday reads `company holiday`, not the name typed
for it), the absence type and half-day flag (never the absence's note), and the balance.

Plans, webhooks, signals, biometrics and coach history are in neither export; they stay
in the database until deleted.

`POST /api/export/import` takes a `/full` file back, a `1.2` one from before billing
budgets were exported, a `1.1` one from before billing was or a `1.0` one from before
absences and adjustments were, into the account that sends it. Re-importing is safe:
projects, sessions and clients are matched by id, a billing by its project, a billing
budget by its client or project, a billable mark by its session, an absence or an
adjustment by its project and date. An import never deletes, so the account's own billing
budgets survive a file without them. The file is checked whole first, and a file that
fails writes nothing: a malformed record, a malformed id included, is a 422; a file
holding projects, sessions or clients of another account is a 409
`BACKUP_OF_ANOTHER_ACCOUNT`; a billing whose project or client, a billing budget whose
client or project, or a mark whose session, is in neither the file nor the account is a
422 naming it; and a client, a billing or a billing budget that its own route would
refuse, against the file laid on the account (an unknown currency, billing on a project
that is not freelance, a budget on a project billed nowhere, and the rest in
[docs/billing.md](docs/billing.md)), is that route's error, naming the record. A restore
is not asked to confirm a change to a past month.

The rest goes through the same rules as the app's own writes, in this order: the
clients; the projects, each as a project write; each project's billing; the billing
budgets; the sessions; the billable marks; then absences and adjustments, against the
projects as restored and the `tz` sent. A project write those rules refuse (a contract that would strand an
adjustment, say) stops the import with that write's error: the clients and the projects
before it in the file are already restored, and nothing after it is written, no billing,
budgets, sessions, marks, absences or adjustments. Fixing the conflict and importing the file
again is safe. A refused absence or adjustment does not stop it (time off on a project that
is no longer a day job, an adjustment outside its contract): it is left out, and the
response lists it under `skipped`.

An API older than the file drops what it does not know without a word: a `1.3` file
imported into an API from before billing budgets restores everything but the budgets, as
a `1.2` file does into one from before billing.

## Deletion

Email <ahmed.elghareeb@proton.me> from the address on your account. I will:

1. Drop every document keyed to your user id across every collection above
2. Revoke active sessions and credentials
3. Reply to confirm

Backups (if any operational backup exists at the time) roll off on the provider's standard window.

## Changes

This file is versioned in the repo. Material changes show up in `git log DATA.md`.
