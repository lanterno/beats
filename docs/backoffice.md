# The control plane

The operator's UI for **running the platform** (#424). Designed 2026-10-31 to
2026-11-04 in roadmaps/backoffice.md; built 2026-11-04. What the public API
enforces about an account — suspension, sign-out everywhere, the day last
seen, per-account limits — is its own file,
[account-controls.md](account-controls.md): a control plane can only control
what the API enforces, and those enforcement points were built first.

**A control plane, not a Django admin and not a dashboard**: pages organised
around what the operator is trying to do — find the account a support mail
came from and act on it, fix an organisation whose owner is gone, see who is
burning the coach budget, see whether storage growth is about to cost money —
never one CRUD form per collection, where the dangerous act is the easiest
thing on the page.

## The line: operational metadata, never user content

The operator's job never requires reading what someone tracked.

| Sees | Never sees |
|---|---|
| Account id, email, created, the day last seen, state | Sessions, their times, their notes |
| Counts: projects, sessions, devices, organisations | Project names, tags, absence notes |
| Which integrations are connected | Any integration's token or fetched content |
| Webhook destinations, by domain | A webhook's full URL, or what was sent to it |
| Coach spend, tokens, model | Any coach conversation or memory |
| Organisation name, settings, members, roles | Clients, rates, amounts, report contents |
| An organisation's audit events: what, by whom, to whom, when | Their details: a reopen's reason, a project's or a team's name |
| Biometric *row counts* | Any biometric value |

The operator can still read any document in Mongo — PRIVACY.md says so rather
than pretending otherwise — and that is why the line is worth drawing: every
question the control plane answers is a `mongosh` session against production
that doesn't happen. **The wall test** (`api/src/test_operator.py`,
`TestOperatorWall`) is how "never user content" is something CI refuses: a
sentinel is planted in every right-column thing — a session's note and its
day decades back, a project's and a team's name, a tag, an absence note, a
client's name and rate, a webhook URL's path, a coach message and a memory,
an integration's token, a biometric value, an audit entry's reason — and
every operator response is searched for it.

What must not happen, held by construction or by that test: no "view as this
user", ever (PRIVACY.md's "we don't watch you" depends on it); no free-text
search over content, and no address in a URL (Cloud Run logs every URL for 30
days — the account lookup takes its address in a POST body); no destructive
act in a request handler; no rule in a command or the runner; no mutation
outside the runner; reads through the named cross-tenant classes, never a
widened `MongoStore._q`; and it does not become customer support with a
deeper tier of access — that would be a new decision with a new PRIVACY.md
sentence, not a patch.

## Architecture: one codebase, two composition roots

One API codebase, one domain layer — *rules implemented more than once are
the ones that drift*, and a control plane is mostly the API's own rules
exercised by a different person — deployed separately, so the isolation a
separate service would have bought is kept:

```
api/src/server.py            the public API        → uvicorn server:app
api/src/operator_server.py   the operator API      → uvicorn operator_server:app
api/src/beats/               the library both compose
```

Not a mode switch, because a switch does not survive contact with `lifespan`:

- **`Database.connect()` builds nothing.** `server.py`'s lifespan calls
  `ensure_indexes` after connecting — the public API is the one deployment
  with the index grant, the operator's collections included — and
  `database.py` no longer imports `beats.settings`, so the whole
  `beats.infrastructure` package imports without `JWT_SECRET` in reach.
- **The operator root never holds `JWT_SECRET`.** `OperatorSettings`
  (`beats/operator/settings.py`) has no field for it, and `operator_server`
  imports none of the public routers, nothing in `beats.auth`, and never
  `beats.settings`. A test imports it in a fresh interpreter and finds
  `beats.settings` out of `sys.modules`; another pins that `server.py`
  imports no operator route — not reachable by construction, not by flag.
- **Its lifespan is honest**: its own `AsyncMongoClient` into `app.state`
  (never the `Database` class attribute, which two apps in one process — the
  test suite — would share and tear down under each other), and nothing
  else: no migrations, no index building.
- **`request.state.user_id` is never set.** The middleware sets
  `request.state.operator`, so a user-scoped dependency imported by mistake
  fails loudly on a missing attribute rather than quietly scoping to the
  operator — the same instinct as `MongoStore._q` stamping a filter nobody
  can forget.

Same image, same `pyproject.toml`, same tests; the Cloud Run service's
command picks the module.

**Queries and commands are different shapes.** Queries — "accounts created
per day", "organisations with no owner" — are aggregation pipelines with no
rule to enforce, so they have no service layer: `MongoOperatorReads`
(`infrastructure/operator_reads.py`, the named cross-tenant class in the
shape of `MongoOrganisationRecords`) behind the `OperatorReads` Protocol
(`beats/operator/reads.py`), frozen dataclasses out. The landing page's
thresholds are named constants there: they decide only what the operator is
shown, never what a user is allowed. No pre-computed aggregates: a pipeline
per request is fine at one operator's scale, and a nightly roll-up would be
the first thing to widen the database user — decided deliberately when it
comes, not slipped in with the page that wants it. Likewise deliberately
absent: a message broker, a separate analytics store, GraphQL, tracing, event
sourcing.

## Commands: objects, through one runner

An audit each handler must remember to write will be missing from the one
action anybody cares about, so a mutation is a command object
(`beats/operator/commands.py`) — name, role, window, confirmation, describe,
execute — and the runner (`beats/operator/runner.py`) is the only path:

1. check the role (`viewer` runs no command — two roles from day one, so a
   second person can look without acting);
2. check the typed confirmation — the account's email, the organisation's
   name; always from the left column of the line, never content; compared,
   never stored; and no defence against cross-site requests, which the
   Origin check holds;
3. `describe()` the subject;
4. run — inline, or enqueue when the command has a window;
5. write `operator_audit` with before and after.

**No rule lives in a command or the runner**: each delegates to whatever
already owns the rule — the account service, the device repository, the
organisation service. There is deliberately no `OperatorService`: a service
in front of the runner would be a second coordinator, and a rule appearing in
either is the signal it was put in the wrong place.

| Command | Runs | Confirmation | Delegates to |
|---|---|---|---|
| `account.suspend` / `unsuspend` | inline | the email / — | `AccountService` (docs/account-controls.md) |
| `account.sign_out_everywhere` | inline | — | the same: `sessions_valid_after` |
| `account.set_limits` / `clear_limits` | inline | — | the same: `account_limits`, the whole document at once |
| `device.revoke` | inline | — | the device repository |
| `control.set` / `control.clear` | inline | — | `MongoPlatformControlsStore` (§ Controls) |
| `erasure_request.log` / `close` | inline | — | `MongoErasureRequests` (*Privacy and compliance*) |
| `deploy.freeze` / `unfreeze` | inline | — | the freeze flag's bucket (§ Deploy freeze) |
| `account.erase` | job, **7 days** | the email | `erasure.erase_account` |
| `organisation.grant_owner` | inline | the name | the operator twin of `set_role` |
| `organisation.begin_closing` / `cancel_closing` | inline | the name / — | the twins (start or move / cancel) |
| `organisation.delete` | job, 1 day | the name | the twin of `delete_organisation` |
| `retention.purge` | job, 1 day | the name, or `all` | `purge_expired_records(organisation_id=…)` |
| `job.cancel` | inline | — | the job store; lifts a suspension only when it was the erasure's |

### The operator's organisation acts

The member methods cannot be called as they stand — `_member` refuses any
caller who isn't one, and in the case these exist for there is no owner at
all — so each has an **operator twin** beside it in `OrganisationService`,
sharing everything after the membership check. The rule is one rule, amending
organisations decisions 10, 29 and 31
([organisations.md](organisations.md)): **the operator acts only for an
organisation with no owner, and only when asked.** While an owner exists —
and a suspended owner counts, or suspending an owner would hand the operator
their organisation — every act is 409 `ORGANISATION_HAS_OWNER`. The request
comes by mail to the PRIVACY.md address, from the address on the requester's
account; the owner role goes to the requester and nobody else, and only to
one holding the highest role any active member holds (409
`REQUESTER_NOT_HIGHEST`) — picking among members is taking a side. A closing
notice may always move **later** (the 30-day minimum protects members; a
later day only gives them more), for owner and operator alike. Deletion needs
no second request — the notice was the request.

Every operator act on an organisation lands in its own audit log under
`actor_kind: operator` (`OrgAuditEvent.actor_kind`: member | system |
operator, derived for rows that predate it; erasure's tombstoning and the
purge write through the one raw writer, `record_org_audit`). Only an admin
reads that log, and the SPA says "by LifePete"; the operator's id is never in
it — the kind is enough. Deletion is the exception that `operator_audit`
alone keeps, since `delete_organisation` deletes the organisation's log with
the rest.

## Jobs: the irreversible work behind a window

`operator_jobs` holds queued commands; a Cloud Run Job
(`python -m beats.operator.jobs`) drains it on Cloud Scheduler's
15-minute tick, finding nothing due and exiting on almost every run. A queued
job is a serialised command — one abstraction, not two mechanisms — and the
job runner is trivial: load the command, run the same runner, which executes
instead of queueing. The role and the typed confirmation were checked once,
by the request that queued it; the job sees no request and holds no allowlist
(it reads settings of its own — its DSN and database name, nothing else — and
is **not** an app in a costume: no `OperatorSettings`, which refuses to load
unless exactly one of the IAP audience and the dev stand-in is set, and a job
has neither). The audit is written under the operator the command carries.

- **Claiming** is one `find_one_and_update`: `queued` past its `run_after`,
  or `running` with a claim over an hour old — a run that died. Overlapping
  runs cannot take the same entry, and re-runs are safe command by command:
  erasure tombstones before it deletes, the purge is idempotent by decision
  30, and a deletion's hand-back takes the assignment with it (#414).
  **A job running past the hour is reclaimed and run a second time,
  concurrently** — `claim()` cannot tell a dead run from a slow one, and the
  re-run safety above is sequential: two concurrent deletions could both read
  a project's holders before either deletes the assignments. Accepted
  (2026-11-14): no command comes within two orders of magnitude of an hour
  at this platform's scale. If a purge or deletion ever approaches it, the
  runner needs a claim heartbeat (refresh `claimed_at` while executing)
  before the window is widened.
- **Rules run at run time, not queue time**: a deletion whose organisation
  gained an owner while it waited is refused then.
- **Failure**: after three attempts an entry is `failed`, shown on the
  landing page and logged at `ERROR`, which a log-based alert
  (`terraform/operator.tf`) sends to `var.alert_email` — a silently failing
  erasure must page somebody.
- **The window** is for the operator's second thoughts and the person's. An
  erasure's is 7 days, and **queueing one suspends the account** with the
  erasure's own wording, which names the day the window ends — so an account
  holder whose address was impersonated in a deletion mail finds out the
  moment they next open the app, inside the week there is to stop it.
  `job.cancel` lifts that suspension, and only that kind — an account already
  suspended for abuse keeps its kind when an erasure is queued on top, so
  cancelling the erasure never opens the abuse door. Three rules keep the
  window one visible, cancellable thing: **one queued job per command and
  subject** (409 `JOB_ALREADY_QUEUED` — two erasures behind one suspension
  would let a cancel lift it while the other ran on schedule);
  **`account.unsuspend` refuses while an erasure is queued** (409
  `ERASURE_QUEUED` — unsuspending around it would leave the account working
  normally, warned of nothing, and still erased on schedule; `job.cancel` is
  the one way out, and it lifts the suspension itself); and **a failed
  queueing side effect cancels the job it queued** — a job standing with no
  suspension would wait out an invisible window while the operator, who got
  an error, believes nothing was queued. A subject that doesn't resolve is a
  404 at queue time, never a waived confirmation: the typed confirmation
  exists precisely for the mistyped id.
- **Erasure must not take the control plane's records with it.**
  `erase_account` ends by sweeping `{"user_id": …}` over every collection, so
  `operator_audit` and `operator_jobs` name their subject as `subject_id`,
  never `user_id`; `account_limits` is keyed on `user_id` on purpose, so the
  sweep takes it. A test pins all three. `operator_audit` stores ids, never
  addresses — it outlives the account it names — and is kept four years, the
  platform's default retention, trimmed by a whole-platform purge.
- **The erasure script stays** as the break-glass path
  (`api/scripts/erase_account.py`): it takes an account id, or lists every
  case-insensitive match for an address and stops — the old exact `find_one`
  could miss the account a mail came from.

## Controls: the switches and the global limits

Shipped 2026-11-14 (stage 2 of what was roadmaps/backoffice.md). In an
incident or a cost spike the operator can stop one kind of work for everyone,
and set the three write limits, without a deploy — from *Access and
controls*, each through its own review and the runner like every mutation.

- **One collection, `platform_controls`**, one document per control keyed on
  its name: four pauses (`coach`, `webhooks`, `imports`, `signups`) and three
  limits (`writes_per_minute_beats`, `writes_per_minute_signals`,
  `imports_per_hour`). Written only by `control.set` and `control.clear`
  (`MongoPlatformControlsStore`, `infrastructure/operator_store.py`). No
  `user_id`: it is the platform's, and erasure's sweep never sees it. It is on
  the `beatsOperator` Atlas role's write list (terraform/README.md).
- **Every pause expires.** `control.set` requires an `until`, at most
  `MAX_PAUSE` (7 days) ahead, and a `reason` for the operator's own page.
  An expired document reads as open, so no job clears it. `signups` has a
  third state: with a `value`, sign-ups are *slowed* to that many an hour
  (counted off `users.created_at` for the last hour, cached a bound) until
  `until`. The limits are settings and do not expire.
- **The public API reads through a cache** (`beats/platform_controls.py`, the
  shape of `auth/account_access.py`, the same 30-second bound, refreshed by
  the auth middleware on every authenticated request): a pause lands within
  30 seconds, and the page says so. **An absent document means open**, which
  is what makes a self-hosted install work with no operator at all. **A
  failed read keeps the last value**, and open if there is none: the switches
  are not a way for a database blip to turn the product off. The module
  imports no settings and nothing under `beats.auth`, because the operator's
  root loads it too.
- **Where each is enforced:** `coach` in `UsageTracker.enforce_budget`, which
  the gateway calls before every model call (inside the chat stream the
  refusal rides as an error event, status gone); `imports` first thing in
  `POST /api/export/import`; `webhooks` beside the per-account switch in
  `dispatch_webhook_event`, where it **drops** — there is no outbox — with
  one `WEBHOOKS_PAUSED_DROPPED` line per event so the loss can be counted;
  `signups` at `POST /register/start` before the user row exists, at
  `/register/verify` for the pause alone (start leaves a row a script could
  finish later; the slow-down counted this visitor at start, and checked
  again would refuse them against their own start) and on the branch of
  `SSOAccountService.sign_in` that would create an account — never a
  sign-in or an added passkey. The three limits sit in `_ceiling`
  (`api/rate_limits.py`): the account's override, then the control, then the
  setting, which stays for self-hosted.
- **Refusals are 409** with `COACH_PAUSED`, `IMPORTS_PAUSED` or
  `SIGNUPS_PAUSED` and fixed text, never the operator's reason. Not 503,
  which would page the owner the moment they pause something on purpose; not
  403 or 429, which `api_rejections` counts. Every client already shows the
  API's `detail` for a code it does not know (docs/account-controls.md § What
  each client does with a refusal), so an old SPA against this API reads the
  sentence.
- **Attention counts anything paused** (`controls_paused`), the queue has a
  row for it due when it ends (`control_paused`, with a runbook), and *Access
  and controls* shows the allowlist read-only beside the switches: the list
  is an environment value, and changing it is a deploy.
- **The limit values** are not in code. The owner's guidance, on the page:
  120 beat writes and 60 signal writes a minute and 10 imports an hour, as
  `api/src/beats/settings.py` recommends — set only after reading the
  per-account rate those routes see in the request log, because the SPA's
  sync engine retries a 429 and a default that refuses a real client is a
  storm.

## Deploy freeze

Shipped 2026-11-14 (stage 6 of what was roadmaps/backoffice.md). During an
incident, the operator stops a merge from shipping on top of it, from
*Releases*, through `deploy.freeze` (a required `until`, at most 7 days, and
a reason) and `deploy.unfreeze` — the runner and the audit like every act.

- **The flag is one object**, `freeze`, in its own small private bucket,
  `<project>-deploy-freeze` (`terraform/operator.tf`, gated on
  `operator_enabled`; `roles/storage.objectUser` for the operator on that
  bucket alone, `objectViewer` for Cloud Build's account). **Never the
  Terraform state bucket**, which holds `JWT_SECRET`. Lines of `key=value`
  (`operator/deploy_freeze.py`): `until_epoch` is what the build compares,
  and the reason is kept to one line so it cannot forge a key. An expired
  flag reads as no freeze, so nothing clears it.
- **The build's check** is the first thing `decide` does in
  `api/scripts/deploy_lock.sh`, holding the mutex, when
  `DEPLOY_FREEZE_OBJECT` is set (`api/cloudbuild.yaml` sets it). In force: the
  decision is `frozen`, the apply is skipped, the lock is released as always,
  and **the build goes red** — green reads as "deployed", and this commit was
  not. A missing bucket or object is no freeze, so a deployment without the
  operator builds as before; a flag that cannot be read for any other reason
  fails the build rather than deploy blind into what may be an incident.
- **After a lift, the frozen commit does not deploy by itself**: re-run the
  newest build, which *Releases* names.
- **The web app is not held.** It ships from the `deploy` job in
  `.github/workflows/ui.yml`, with credentials that cannot see the bucket; the
  page and the review both say "the web app can still ship". Holding it too
  would need `firebase-deployer` read on the bucket and a check in that job.
- Off Google Cloud, or with no bucket (`OPERATOR_FREEZE_BUCKET`, set by
  Terraform), the commands answer 409 `FREEZE_UNAVAILABLE` and the panel says
  the builds cannot be held back from here.

## Decided against, or postponed

The redesign's last open questions were answered on 2026-11-14, when its last
stage shipped and its roadmap went. None of these is built, each on purpose,
and a screen that offered one would be the same bug as a control the API
cannot serve.

- **Rolling a release back from the back office** — postponed by the owner on
  2026-11-08. A rollback stays what it is: revert on `main`. A build never
  rolls back, because `deploy_lock.sh` skips a commit the live one already
  contains. It would take `run.services.update` on the operator's account,
  which holds nothing like it, and a way to square a moved traffic split with
  Terraform, whose next apply owns the service and would move it straight
  back. Reopen it only if a real incident shows that reverting on `main` was
  too slow, measured from the merge to the live revision.
- **A required reason and reference on every command** — no. The record is
  you, the command, the subject and the two sides; a reason that had to be
  typed would be typed badly, and the one command whose reason matters
  (suspension) already asks for it. The deploy freeze, a pause and a status
  post carry theirs because somebody else reads them.
- **Incidents and write-ups** — no, not as a record here. The status page
  tells customers; a write-up is prose, and belongs in the repository's
  history with the fix. If one is ever kept, it can prefill a status post.
- **A list of restrictions in force across accounts** — no. Each account's
  page shows its own suspension and limits, and a list across accounts is
  the browsable account list the line refuses; nothing records why, or when
  to look again, for the same reason.
- **An audit of each lookup** — no. Opening an account is a read, and reads
  are not recorded: a write on every read path would slow the one thing the
  operator does most, and a log of who looked at whom is a record about
  people the control plane deliberately does not keep. The recent list is
  ids in `localStorage`, visible to nobody else.
- **Snoozing or finishing a queue item** — no. A row is the condition, and
  it leaves when the condition does; stored state per row would let a row be
  ticked off while the thing itself still stands.

## Authentication

Google IAP is in front, on the Cloud Run service; the app verifies the signed
assertion itself (`beats/operator/iap.py`, built the way `auth/oidc.py` is —
an async httpx fetch of Google's key set with a TTL cache, `jwt.PyJWK` per
key, never the synchronous `PyJWKClient`): ES256 and no other, a published
`kid` (one refetch on an unknown one, for rotations), `iss`
`https://cloud.google.com/iap`, the service's audience with the project
number, 30 seconds of leeway. An unreachable key set is a 503, never a 401.

The assertion's `sub` — stable; the email is shown, never matched, the same
reason an SSO identity is keyed on issuer + subject — is matched against the
allowlist in `OperatorSettings`, `viewer` or `operator` beside each. **IAP's
IAM binding says who reaches the app; the allowlist says what they may do**,
so an IAM grant made by mistake reaches a 403. Locally
`BACKOFFICE_DEV_OPERATOR=<sub>` stands in for the assertion, the way
`BEATS_TEST_ENV` stands in for testcontainers: exactly one of it and the
audience may be set, or the settings refuse to load — a stand-in left in a
deployment stops the deploy instead of replacing the wall.

**Before a second person goes on the allowlist**, even as a `viewer`,
PRIVACY.md's "I … am the only operator" sentence names them, and the DPA's
confidentiality term (roadmaps/legal/dpa.md) says who else sees an
organisation's members. The allowlist is read-only on the Access page for the
same reason: adding someone is a deploy, and the privacy text goes first.

The browser's credential is IAP's cookie, which a request another site's page
starts would carry too. So every command is a POST with a JSON body, no GET
changes anything, and the app refuses a write — the account lookup included,
though it reads — whose `Origin` is missing or not its own, or whose
`Sec-Fetch-Site` isn't `same-origin` where the browser sends one. The typed
confirmation is no defence here; a forging page sends it as easily as the
operator types it.

## Deployment

**One service, behind Cloud Run's own IAP; no load balancer** — a global
forwarding rule costs about $18 a month standing, which at one operator buys
nothing a person would notice. The separation is in the repo and the build;
revisit if the back office ever needs to deploy apart from the API.

- `beats-operator` runs the API's image with the `operator_server:app`
  command, at zero minimum instances, `iap_enabled`, IAP's service agent its
  only invoker, a service account of its own (`terraform/operator.tf` — never
  the Compute Engine default, which holds `roles/editor` and reads the whole
  state bucket, `JWT_SECRET` included). Its DSN is the narrow Atlas user's,
  from `beats-operator-dsn`; the job's is its own user, from `beats-jobs-dsn`
  — each credential rotates alone. The secret containers and bindings are
  Terraform's; the values are added by hand and never pass through it.
- **The hostname is `backoffice.lifepete.com`**: a Cloud Run domain mapping and
  a DNS-only CNAME, the shape of `api.lifepete.com`, with no load balancer.
  Google's IAP pages name only `run.app` URLs and load balancers, so IAP
  covering a mapped hostname is something we observed rather than something
  Google promises: on 2026-11-08 an anonymous request there went to Google's
  sign-in. The `run.app` URL stays up behind the same IAP, but `OPERATOR_ORIGIN`
  is the hostname, so a write from it answers 403.
- **The UI** (`backoffice/`) is its own pnpm workspace on the toolchain `ui/`
  runs — React 19, TypeScript 7, Vite, Tailwind, TanStack Query, Biome, its
  own `tools/openapi-types` on a TypeScript 5 — generated from
  `dump_openapi_operator.py` with a drift check in pre-push and CI
  (`.github/workflows/backoffice.yml`, no deploy job). It **wears the app's
  look**: the sky, the panels and the two hours, with the tokens copied into
  `client/tokens.css`. Until 2026-11-08 it was plain grey on purpose, so an
  operator could never be unsure which surface they were on; that job now
  falls to a "Back office" mark on every page at every width, and to the
  tab's title. Its tables are tighter than the app's, being lists to scan.
  The two typefaces come from Google Fonts, the one thing these pages load
  from another origin. Vite builds into
  `api/src/beats/operator/static/` (gitignored), which Cloud Build fills in a
  step before the image build, so the Dockerfile's existing `COPY src/`
  carries it and `operator_server` serves it: one origin, one IAP session. A
  back-office-only change rebuilds and redeploys `beats-api` with the same
  code, under the same deploy lock — accepted: one more revision, not a
  second pipeline. Locally, `just run-operator-locally` serves :7998 and the
  Vite dev server on :8081 proxies `/api/operator` to it.
- **Not in the self-hosted bundle.** IAP doesn't exist outside GCP, and
  shipping a privileged surface with a weaker auth story is how one ends up
  with a default credential on the internet. If it is ever wanted there, that
  is a separate decision with its own authentication design.

The hand-made prerequisites — the Atlas users and roles, IAP's custom OAuth
client (the project sits in no Google Cloud organisation, so no API creates
one), the secrets' first versions, and the `operator_enabled` flip — are
terraform/README.md's *Operator Deployment* section; production's was turned
on by them on 2026-11-08.

## The pages, by the job they serve

The pages were reorganised around the work on 2026-11-14 (the mock they were
drawn from is in [backoffice-mock/](backoffice-mock/)). A page appears in the sidebar only once it is
built: a nav entry to a screen that does not exist is a promise the API
cannot keep.

- **Today**, the landing page: one sentence saying what matters, read off the
  queue; the next few rows due, each with the way to it; the jobs waiting out
  a window; the back office's last few commands; storage and this month's
  coach spend; and one link — the accounts a per-account write limit refused,
  which is a log query because nothing stores a refusal (see *Trust and
  safety* below). The deploy-state card links to the Cloud Run console until
  roadmaps/secret-manager.md lands.
- **Work queue** (`GET /api/operator/queue`): the rows behind the Attention
  counts (`GET /api/operator/attention`, which still badges the sidebar),
  ids and dates only, each with a due date from the constants in
  `operator/reads.py` (`queue_due`). The conditions are organisations with no
  owner, and those whose every owner is suspended (the operator doesn't act
  for the latter — they have an owner — but somebody should know); failed
  jobs, and queued jobs, due when their window ends; approvals superseded and
  never reopened, due 30 days after; absence requests pending, due 14 days
  after; accounts at 80% of their coach cap. The last two kinds are one row
  per organisation, with a count and no member named, and are listed before
  they are due. A row with no stored date is due when it is read and shows as
  today, never overdue. **Nothing is stored**: there is no snooze and no
  "done"; a row is the condition, and leaves when it clears. An erasure
  request the operator logged (see *Privacy and compliance*) is a row too,
  due 14 days after the mail arrived, until an erasure is queued for its
  account or it is closed; a paused control is a row due when it ends.
- **The palette** (⌘K, in the top bar): goes to a page, opens a command's
  review for an account named by its whole id, and finds one account by its
  whole address through the same `POST /accounts/lookup`. Pages are filtered
  by what is typed; people never are — a fragment finds no one. A command
  never runs from it, and an address is forgotten when the dialog closes.
- **Review** (`/review/{command}/{subject}`): every account command is carried
  out from a page of its own, showing what it would change
  (`POST /commands/{name}/preview`, which writes nothing and refuses a
  `viewer` as the act does), who notices and whether it can be undone (fixed
  text per command, `client/shared/commands.ts`), and the typed confirmation.
- **Access and controls**: the switches and the global limits (§ Controls),
  each thrown from its review page; who can get in, read off the allowlist;
  what each role can do; and the access review as a list to read down, since
  nothing records that it was done.
- **Runbooks**: static pages in the bundle (`client/shared/runbooks.ts`), each
  with a `reviewed_on` and marked stale after six months, linked from the
  queue rows they fit. The alert runbooks restate the `documentation` blocks
  in `terraform/alerts.tf`, and change with them. A bad release's says to
  revert on `main`. Nothing records when one was last used.
- **Accounts**: found by exact email (case-insensitive — sign-up stores an
  address as typed under a unique index with no collation, so `Ana@` and
  `ana@` can be two accounts and a mail from either spelling must find both)
  or by id; never a browsable list or a prefix search, which would serve
  fishing. One account shows its states, counts, a storage estimate
  (`$bsonSize` summed per user-keyed collection, computed for one account on
  this page only, never for a list), coach spend against its cap, connected
  integrations — and its actions. Which identities it holds per provider is
  a fact the account stores and fair to show; which door a sign-in used is
  deliberately not kept, and must not grow out of this page. **No
  subject-access export**: a person exports everything themselves, and an
  export the operator generates would carry someone's content through the
  one surface built never to.
- **Organisations**: rosters, states, timesheet counts, and the audit without
  each event's `details`; the three acts, offered only while no owner is
  left.
- **Trust and safety**: outliers rather than guessed thresholds — coach spend, flow
  windows today, sessions created, report links minted (the only public path
  serving a user's data), webhook destinations by domain (outbound HTTP from
  our servers is ours to answer for), devices per account, signups per day.
  Abuse that shows in requests rather than accounts is already counted and
  alerted on in Cloud Monitoring.

  **Sign-ups from one network** (shipped 2026-11-14, stage 3 of what was
  roadmaps/backoffice.md): the hour's finished sign-ups against the median
  of the same hour of the week over the last eight weeks, and the largest
  network's share of the hour, shown only at or above `SIGNUP_NETWORK_MIN_GROUP`
  (5). The network is the visitor's address cut to its /24 (IPv4) or /48
  (IPv6) and HMAC-hashed under a key derived for the UTC day — from
  `JWT_SECRET`, which the public API already holds and the operator
  deployment never does, so the operator can never compute a key and never
  test a guess, and **no new secret or setting is needed**: a deployment that
  can sign a session runs the signal (`auth/signup_networks.py`). Only a
  counter is stored (`signup_network_counts`: hour, key, `started`,
  `completed`, 48-hour TTL), written best-effort from the two passkey doors
  and the SSO branch that creates an account. The page says "Network A",
  never the key, and says in words that offices, universities, carrier
  networks and an organisation onboarding its staff all look like this. The
  action is the `signups` control with the key as its `network`: a ceiling an
  hour for that network alone, read off the signal's own counter, that slows
  and never blocks and ends at the next UTC midnight at the latest, when the
  key stops matching. Why stored, when the two signals below are "logged and
  counted, never stored": those are facts about one account's request; this
  holds no account at all, and logging it would show the operator raw
  addresses or need a metric label per network. PRIVACY.md and DATA.md say
  what is kept, for how long and why. Behind a self-hosted nginx every
  visitor is one network, which only makes the signal quiet.

  Two of its signals are **logged and counted, never stored** (decided
  2026-11-07). A per-account write limit's refusal
  (`WRITE_LIMIT_REFUSED`, emitted from the one 429 handler in
  `api/src/beats/api/errors.py`) and a restore's size (`IMPORT_RECEIVED`,
  `api/src/beats/api/routers/export.py`) are facts about a request, not
  about what an account holds; a stored count of a person's refusals would
  be a history of what they did, which is the same thing the account page
  refuses when it declines to keep which door a sign-in used. So each is a
  line in the API's own log, a log-based metric in
  `terraform/monitoring.tf` (`write_limit_refusals` by route,
  `import_bytes` as a distribution), and a link from the page rather than a
  row — the shape Capacity already uses for latency. The account is in the
  line and in no metric label: per-account labels are unbounded
  cardinality, and "which accounts, this week" is the log query the
  Today page links to. The address-keyed doors in `routers/auth.py` are
  deliberately out of both: scanners exhaust them all day, and
  `api_rejections` already counts them. Until a `WRITES_PER_MINUTE_*`
  ceiling is set, the refusal signal counts nothing, which the page says.
- **Capacity**: documents and storage per collection (`$collStats`), the
  coach's platform cost by day and model with the cache-read inputs, and
  live health with refused writes per route.
- **Live health** (shipped 2026-11-14, stage 4 of what was
  roadmaps/backoffice.md), on Today and Capacity through `GET
  /api/operator/health`: availability over the last day (the uptime checks)
  against the **99.5% a month target** (decided 2026-11-14: one region,
  30-second cold starts and one operator make 99.9% a budget the first bad
  deploy would spend), the share of 5xx and p95 latency over the last hour,
  instances against their ceiling, and refused writes per route. Read by
  `GoogleMonitoring` (`operator/health.py`) over plain `httpx`, behind the
  `MonitoringSource` port, with `roles/monitoring.viewer` on the operator's
  account (gated on `operator_enabled`). **Nothing to configure**: the
  project and the token come from the metadata server, and the service name
  and ceiling (`OPERATOR_API_SERVICE`, `OPERATOR_API_MAX_INSTANCES`) are set
  by Terraform, with defaults. Cached a minute in the process; a Google
  failure answers the last figures and their age, a failure is cached too,
  and off Google Cloud the panel says "unavailable" with the console link —
  never an invented number, never a broken page. Nothing is stored. Not
  shown, on purpose: Google's open-alert list (`alerts.list`, in preview on
  2026-11-08; the console link stands in) and the job runner's last run (a
  run that finds nothing writes nothing, so no source holds it).
- **Releases** (shipped 2026-11-14, stage 5 of what was
  roadmaps/backoffice.md; `GET /api/operator/releases`): when something
  breaks, what shipped just before it. The API's last ten builds from Cloud
  Build's `builds.list` (`roles/cloudbuild.builds.viewer`, gated on
  `operator_enabled`), each with its commit and GitHub subject; the commit
  the API was deployed with, the operator's own image tag set by Terraform
  (`OPERATOR_API_COMMIT`) and labelled "as deployed", since a revision that
  failed to become ready leaves the previous one serving; and the web app's
  live commit, from the `version.json` its build writes (`ui/vite.config.ts`,
  only when `VITE_GIT_SHA` is set), fetched from `OPERATOR_WEB_ORIGIN`. A
  web app on another commit than the API is normal and said so. Each source
  answers on its own, cached a minute (`ReleasesCache`): one that fails keeps
  its last answer and is named, and subjects are cached for good. Nothing
  moves traffic, and nothing reads the API's Cloud Run service; a bad build
  links to the runbook for reverting on `main`. A build viewer can read every
  step's arguments, so `api/cloudbuild.yaml` must never put a secret in one.
  Firebase's own release list is deliberately not read: `version.json`
  already says what is live, without another grant or a site id. Today says
  what each half is running.
- **Jobs and windows**: the job queue with cancel. A failed job has no
  re-run: three attempts is terminal, and the way back is to queue the
  command again.
- **Privacy and compliance**: the platform-wide retention purge behind the
  typed word `all`, and **the erasure request log** (shipped 2026-11-14,
  stage 8 of what was roadmaps/backoffice.md). A request that arrives by
  email gets a date the day it arrives (`erasure_request.log`: the day, a
  reference the operator chose, the account by `subject_id` — never
  `user_id`, or erasure's sweep would take the record that it was asked for
  — and never an address, which the command refuses), so the legal month is
  visible before anything is queued. Its state is read off the job queue,
  never stored: open, erasure queued, erasure ran, closed. A request open
  with nothing queued for `ERASURE_REQUEST_ATTENTION_DAYS` (14) counts on
  Attention and sits on the queue; `erasure_request.close` ends it with a
  reason (erased, no account, withdrawn), and a closed row goes a year later
  by TTL (`MongoErasureRequests`, `erasure_requests` on the Atlas grant). The
  earlier reason for not counting requests — that it would take an in-app
  request — does not hold for a log the operator keeps.
- **Audit log**: the operator audit — readable, filterable, editable by
  nobody, kept four years. It holds what ran: the runner writes the row after
  a command succeeds, so a refused or failed command is not in it.
