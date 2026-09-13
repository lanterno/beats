# Data handling

The full inventory of what Beats stores, where it stores it, and how to get it back out. For a plain-English overview, see [PRIVACY.md](./PRIVACY.md).

## Where data lives

Beats runs in two places, and each has its own database. **home.space** is the
primary: `compose.home.yml` on the home network. **lifepete.com** runs on Google
Cloud. See Infrastructure in [CLAUDE.md](./CLAUDE.md).

| Layer    | home.space                                                                 | lifepete.com                                                          | What it holds                                        |
|----------|----------------------------------------------------------------------------|-----------------------------------------------------------------------|------------------------------------------------------|
| API      | Container on the home network                                              | Google Cloud Run                                                      | Stateless — request handling only                    |
| Database | MongoDB container, `beats-home-mongo-data` volume, not published on the LAN | External MongoDB cluster, reached by the connection string Terraform takes | Every collection listed below                        |
| Web app  | nginx in the same stack, one origin with the API                           | Firebase Hosting                                                      | Static assets only                                   |
| Secrets  | `api/.env` on the host                                                     | GCP Secret Manager                                                    | OAuth client secrets, Anthropic API key, infra creds |
| Logs     | Container logs (`just logs`)                                               | Google Cloud Logging                                                  | Request logs (no request bodies)                     |
| Backups  | `just backup <dir>`: a gzipped mongodump archive, taken on demand          | None configured in this repo                                          | The database                                         |

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
  derived from them on request, no calendar is stored); `opening_balance_hours`;
  `ended_on`. On a day job whose contract governs the week, `weekly_goal` is cleared at
  startup: the contract is the goal.
- **Absences**: one document per day off on a day-job project — `user_id`, `project_id`,
  `date`, `half_day`, `type` (`vacation`, `sick`, `other`), `note`. Unique on
  `(user_id, project_id, date)`, so a second absence on a day replaces the first.
- **Beats (sessions)**: start, end, project id, source (manual / daemon / editor), tags, notes
- **Timer state**: the currently-running beat per user
- **Plans**: weekly plans — a per-project hour target for a given week
- **Webhooks**: target URLs and which timer events they subscribe to. Deliveries
  are fire-and-forget; no delivery log is kept.

### Intelligence and coach

- **Signals**: flow windows and summaries emitted by the daemon
- **Focus scores**: per-day scores derived from signals
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

- **In transit**: on lifepete.com, HTTPS to the API and TLS to the MongoDB cluster. On home.space the API reaches MongoDB over the stack's internal Docker network without TLS; the database is not published on the LAN.
- **At rest**: on lifepete.com, the MongoDB cluster's encryption at rest and GCP's for Secret Manager. On home.space, only what the host's disk provides: Beats does not encrypt the Mongo volume or `api/.env`.
- **Application-level encryption**: Beats does not currently apply a second encryption layer to integration tokens beyond what MongoDB provides. If you need that, do not connect integrations.

## Retention

Beats does not auto-delete anything. Beats, notes, coach history, and biometrics persist until you delete them or delete your account.

## Export

`/api/export` returns the authenticated user's projects — contract included — and sessions: `/full` as JSON, `/csv/sessions` as a CSV of the completed sessions alone. Nothing is held back behind a tier, but nothing else is in it yet either: absences, plans, webhooks, signals, biometrics and coach history stay in the database until deleted.

## Deletion

Email <ahmed.elghareeb@proton.me> from the address on your account. I will:

1. Drop every document keyed to your user id across every collection above
2. Revoke active sessions and credentials
3. Reply to confirm

Backups (if any operational backup exists at the time) roll off on the provider's standard window.

## Changes

This file is versioned in the repo. Material changes show up in `git log DATA.md`.
