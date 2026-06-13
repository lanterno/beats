# Data handling

The full inventory of what Beats stores, where it stores it, and how to get it back out. For a plain-English overview, see [PRIVACY.md](./PRIVACY.md).

## Where data lives

| Layer            | Provider                | What it holds                                            |
|------------------|-------------------------|----------------------------------------------------------|
| API              | Google Cloud Run        | Stateless — request handling only                        |
| Primary database | MongoDB (GCP)           | Every collection listed below                            |
| Web app          | Firebase Hosting        | Static assets only                                       |
| Secrets          | GCP Secret Manager      | OAuth client secrets, Anthropic API key, infra creds     |
| Logs             | Google Cloud Logging    | Request logs (no request bodies)                         |

## What's stored, by domain

### Account and auth

- User document: id, email, display name, created-at
- WebAuthn credentials: public key, credential id, sign counter, device label
- Refresh-token records for JWT rotation

No passwords are stored — Beats does not have a password login path.

### Work data

- **Projects**: name, color, tags, archive flag
- **Beats (sessions)**: start, end, project id, source (manual / daemon / editor), tags, notes
- **Timer state**: the currently-running beat per user
- **Intentions**: daily and recurring intentions, completion state
- **Daily notes**: end-of-day mood, energy, free-text note
- **Plans**: weekly plans, reviews, streaks
- **Webhooks**: target URLs and delivery history
- **Auto-start rules**: editor/repo patterns that trigger a beat

### Intelligence and coach

- **Signals**: flow windows and summaries emitted by the daemon
- **Focus scores**: per-day scores derived from signals
- **Inbox items**: surfaced patterns and suggestions
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

- **In transit**: TLS everywhere (HTTPS to the API, TLS to MongoDB)
- **At rest**: MongoDB-managed encryption-at-rest on the storage volume; GCP-managed for Secret Manager
- **Application-level encryption**: Beats does not currently apply a second encryption layer to integration tokens beyond what MongoDB provides. If you need that, do not connect integrations.

## Retention

Beats does not auto-delete anything. Beats, notes, coach history, and biometrics persist until you delete them or delete your account.

## Export

`/api/export` returns the full dataset for the authenticated user as CSV or JSON. There is no curated subset and no extra fields hidden behind a paid tier.

## Deletion

Email <ahmed.elghareeb@proton.me> from the address on your account. I will:

1. Drop every document keyed to your user id across every collection above
2. Revoke active sessions and credentials
3. Reply to confirm

Backups (if any operational backup exists at the time) roll off on the provider's standard window.

## Changes

This file is versioned in the repo. Material changes show up in `git log DATA.md`.
