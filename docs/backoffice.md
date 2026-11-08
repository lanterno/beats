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
  (`.github/workflows/backoffice.yml`, no deploy job). It is deliberately
  **not the sky**: dense, plain, one neutral palette — an operator should
  never be unsure which surface they are on. Vite builds into
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

- **Attention**, the landing page: a count per row, and one link — the
  accounts a per-account write limit refused, which is a log query because
  nothing stores a refusal (see *Abuse* below). The counts are
  organisations with no owner, and those
  whose every owner is suspended (the operator doesn't act for the latter —
  they have an owner — but somebody should know); queued jobs inside their
  window and failed jobs; approvals superseded and never reopened for more
  than 30 days; absence requests pending more than 14 days; accounts at 80%
  of their coach cap. Erasure requests are deliberately not counted:
  PRIVACY.md has a person ask by email, and counting them would take an
  in-app request — a product change, not a control-plane page.
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
- **Abuse**: outliers rather than guessed thresholds — coach spend, flow
  windows today, sessions created, report links minted (the only public path
  serving a user's data), webhook destinations by domain (outbound HTTP from
  our servers is ours to answer for), devices per account, signups per day.
  Abuse that shows in requests rather than accounts is already counted and
  alerted on in Cloud Monitoring.

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
  Attention page links to. The address-keyed doors in `routers/auth.py` are
  deliberately out of both: scanners exhaust them all day, and
  `api_rejections` already counts them. Until a `WRITES_PER_MINUTE_*`
  ceiling is set, the refusal signal counts nothing, which the page says.
- **Capacity**: documents and storage per collection (`$collStats`), the
  coach's platform cost by day and model with the cache-read inputs. Latency,
  error rates and instance counts are Cloud Monitoring's — linked, not
  rebuilt.
- **Compliance**: the job queue with cancel, the platform-wide retention
  purge behind the typed word `all`, and the operator audit — readable,
  filterable, editable by nobody, kept four years.
