# Account controls

What the API enforces about an account itself: suspension, sign-out
everywhere, the day last seen, and per-account limits. Shipped 2026-11-04 as
step 1 of the control plane ([backoffice.md](backoffice.md)), whose premise
it serves: a control plane can only control what the API enforces. The
control plane's commands delegate to the same rules
(`beats/domain/accounts.py`), and `api/scripts/suspend_account.py` stays as
the break-glass path beside them.

Each act means one thing, and they deliberately do not overlap:

- **sign-out ends sessions** — devices stay paired;
- **revoking ends one device** (`DeviceRegistration.revoked`, which predates
  this work);
- **suspension ends both.**

## Suspension, end to end

`User.suspended_at` set is what "suspended" means; `suspended_by`,
`suspended_kind` (`abuse`, `erasure`, `other`) and `suspended_reason` ride
with it. The reason is the operator's own and is never shown to the person.

The refusal is the same everywhere: **403 `ACCOUNT_SUSPENDED`** in the error
envelope — not a 401, which would sign the person out with the words for an
expired session. The `detail` says what to do, worded around the brand's
contact address (`CONTACT_EMAIL`, stamped from `shared/brand.json`):
"This account is suspended. Write to {contact} from this account's address."
An `erasure`-kind suspension says instead that the account is being deleted on
the day its 7-day window ends (`suspended_at` + `ERASURE_WINDOW_DAYS`), so an
account holder whose address was impersonated in a deletion mail finds out the
moment they next open the app, inside the week they have to stop it
(`suspension_detail` in `beats/domain/accounts.py`).

Where it is refused:

- **The middleware, on every request carrying a valid session**, public path
  or not — the session branch runs before the `is_public` check, which is what
  covers SSO linking.
- **The device branch**, after the revocation check and before the path
  allowlist. A device token has no expiry by design, so an account whose
  daemon still writes flow windows has not been suspended.
- **The doors the middleware never sees**, each refusing only *after* its
  ceremony or exchange succeeds, so only someone who can actually sign in
  learns of the suspension: passkey login, registration verify on an existing
  account, `POST /api/auth/sso/complete`, and the pairing exchange (a code
  made before the suspension must not mint a device token that starts working
  the moment the suspension lifts).
- **`/api/reports`**: a suspended account's report links answer that route's
  one 404. Suspension is for abuse, and a public link serving the account's
  data is the account acting.

What it does not touch: an organisation's record of the person (the stamped
rows it already reads, and an admin entering time on the assignment — that is
the organisation acting), and background work, of which there is none per
account.

An account that no longer exists (erased while a token lived) answers **401
`INVALID_TOKEN`** on the session branch — the session ended with the account,
and a client's sign-out handling of a 401 is right for it — and **403
`DEVICE_REVOKED`** on the device branch, which erasure's deletion of the
registrations already produced.

## Sign-out everywhere, and auth_time

`User.sessions_valid_after` set means every session whose sign-in is older is
refused (401 `INVALID_TOKEN`). One field; no token list to share between
instances.

The comparison is against the token's **`auth_time`** claim — when the passkey
or SSO sign-in happened — which `refresh_token` copies unchanged, so a
refreshed token is exactly as old as the sign-in behind it. `iat` could not
serve: every refresh renews it, so an actively refreshed session would always
read newer than the cut and outlive it for good. A session token without
`auth_time` (minted before the claim existed) is refused outright by
`validate_session_token`: a refresh would have nothing to copy, and reading
such a token's `iat` would let a tab that renews every 55 minutes outlive
every sign-out.

## The cached lookup, and the day last seen

Suspension and the sign-out cut are checked on every authenticated request.
Done naively that is a Mongo round-trip per request, so the account's auth
state is cached the way a device's revocation verdict is
(`beats/auth/account_access.py`, the shape and reasoning of
`device_access.py`): process-local, 30-second TTL, the token's signature still
checked every time. A suspension or sign-out written by another process — the
script today, the operator deployment later, which cannot drop entries here —
takes effect within the TTL on every instance. The account's `account_limits`
ceilings ride the same entry: one cache, two reads on a miss, for everything
that needs the account on the request path.

The same lookup stamps **`User.last_seen_on`** — the day (UTC) a request last
carried the account's credential. A date, deliberately not a time: a session's
times are the account's own business, and a day is all "is this account in
use?" needs. Written with a conditional update at most once a day, however
many instances see the account. A device registration's `last_seen` (a BSON
datetime; `update_last_seen` used to write an ISO string and had no caller)
is stamped the same way on the device cache's miss, also at most once a day.

## Per-account limits

One `account_limits` document per account (`AccountLimits` in
`domain/models.py`), present only when something is overridden, and keyed on
`user_id` **deliberately** so erasure's sweep takes it with the rest of the
account. `null` on a field means the global setting decides.

- **Write ceilings** — the first rate limits on the routes a hostile or
  broken client can flood, keyed on the account rather than the address
  (`beats/api/rate_limits.py`): one shared bucket over `POST`/`PUT`/`DELETE`
  `/api/beats`, one over the daemon's `POST`s under `/api/signals`, one on
  `POST /api/export/import`. The global defaults are settings
  (`WRITES_PER_MINUTE_BEATS`, `WRITES_PER_MINUTE_SIGNALS`, `IMPORTS_PER_HOUR`),
  **off until set**: before turning one on, check it against the per-account
  rate the routes actually see in the request logs — a default that refuses a
  real client is a 429 storm in the SPA's sync engine, which retries 429. The
  recommended starting values (120, 60 a minute and 10 an hour — about ten
  times the clients' own cadence) are the comment in `settings.py`. Counted
  per instance, like the IP limits and by the same decision (#391, the
  comment above `limiter` in `routers/auth.py`). slowapi's limit callable is
  synchronous, so the ceiling is read off the cached account lookup the
  middleware filled on the way in.
- **The coach's ceiling** (`coach_monthly_budget_usd`) is read before the
  global by `UsageTracker.enforce_budget` and by `GET /api/coach/usage`, so
  the SPA's usage bar and the refusal agree.
- **`webhooks_disabled`** turns an account's webhooks off at dispatch —
  registered ones fall silent — and answers 403 `WEBHOOKS_DISABLED` on
  create. On the account, not the webhook, so deleting and re-creating the
  same URL gets around nothing; `Webhook.active` stays the owner's own flag.

## What each client does with a refusal

No client drops a write because the account is suspended: suspension can be
undone, and dropping would make it delete the person's own writes.

- **SPA.** `ACCOUNT_SUSPENDED` from any call — refresh and `/me` included —
  shows the API's sentence as a full-page notice
  (`shared/lib/suspension.ts`, the gate in `app/App.tsx`), stops the sync
  engine's polling until the page reloads, and ends the session as a sign-out
  would, without the 401 path's redirect into a sign-in loop. Separately, and
  standing on its own: the IndexedDB write queue is the browser's, not the
  account's, so every queued write is stamped with the account it was made
  under (the token's `sub`, read synchronously — the user key waits on
  `/me`), and the drain replays only the signed-in account's rows. A write
  queued before a suspension waits, under its own account, for the next
  sign-in that is allowed; rows from before the stamp existed replay as they
  always did.
- **Daemon.** On `ACCOUNT_SUSPENDED` or `DEVICE_REVOKED` — the envelope's
  code, carried by the client's typed `APIError` — a `RefusalGate`
  (`internal/client/gate.go`) shared by the flush loop, the timer-context
  poller and the drift posts pauses all API traffic, logs the refusal once,
  and lets one call through every ten minutes as the probe that notices the
  refusal lifting. Windows flushed meanwhile are held in the retry buffer, so
  a short suspension loses nothing; past its 32-window cap the oldest go —
  accepted, they are derived signals, not the person's record. `beatsd
  status` and `doctor` name the refusal ("refused (account suspended) — …")
  from their own calls; `status --json` carries `api.refused`.
- **Companion.** Its queue keeps any 403 (rule 7,
  [companion-offline.md](companion-offline.md)). `isChatForbidden` and
  `needsNewerServer` read the envelope's code (`DEVICE_PATH_FORBIDDEN`), not
  the bare status — a suspended account's 403 is not an old server, and no
  newer server would fix it. `ACCOUNT_SUSPENDED` shows the API's sentence as
  a banner over the shell: the client's one error path sets the notice, and
  the next timer poll that succeeds clears it.
- **Wall clock.** On a 403 it drops from its 10-second poll to one a minute —
  the slow poll is the probe — pauses heartbeats, and repaints a stale
  running timer as the idle face.
