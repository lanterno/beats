# The control plane — what is still open

The operator's control plane (#424) **shipped on 2026-11-04** and was turned
on in production on 2026-11-08. What is built, and why, is in
[docs/backoffice.md](../docs/backoffice.md), with what the public API enforces
in [docs/account-controls.md](../docs/account-controls.md) and the hand-made
prerequisites in terraform/README.md § *Operator Deployment*.

On 2026-11-08 the owner reviewed a redesign of the whole back office and
answered what it assumes but nothing provides yet. This file turns those
answers into stages that someone with no memory of the conversation can start
from. Stages 1 and 2 — the pages reorganised around the work, and the
switches with the global limits — shipped on 2026-11-14 and are in
docs/backoffice.md § *The pages* and § *Controls*; no other stage has started.

**The owner's inputs were decided on 2026-11-14**, so no stage below waits
on a decision; each says what was decided and why, and what is still done by
hand.

| | Work | The owner's answer | Blocked by | Needs the owner for |
|---|---|---|---|---|
| 3 | Signups from one network | Keep, and improve | Nothing | Setting the secret; approving the PRIVACY.md sentence drafted below |
| 4 | Live health from Cloud Monitoring | Build | Nothing | Nothing (target decided below) |
| 5 | Release history | Build | Nothing | Nothing |
| 6 | Deploy freeze | Build | Nothing | Nothing |
| 7 | Customer updates | Build | Its own file, [status-page.md](status-page.md) | The wording of the PRIVACY.md sentence |
| 8 | Erasure request log | Wanted, not urgent | Do it last | Adding `erasure_requests` to the Atlas role |
| – | Rolling a release back from the back office | Postponed | [Below](#postponed-rolling-a-release-back) | |
| – | Reasons on commands, incidents, restrictions in force, an audit of lookups | No answer given | [Below](#not-decided-the-new-records) | The decision |

The numbers are a suggested order. Apart from what the table says, any stage
can be picked up alone. Stage 1's screens are built; the rows below marked
"then 3 and 4 add to it" are what later stages add to a built page. Five
smaller items from before the redesign are at the end of *Work*.

**By hand, before stage 2 is used in production:** add `platform_controls`
to the `beatsOperator` Atlas role's writes (terraform/README.md § *Operator
Deployment*). Until then `control.set` fails on the write and nothing else
is affected. The limit values are set from the page, not in code: 120 beat
writes and 60 signal writes a minute and 10 imports an hour are the
recommendation, after reading the per-account rate in the request log.

## The design

**The mock** is in [backoffice-mock/](backoffice-mock/): a picture and the source
of every screen, and how to read them, with no Claude account needed. Every
figure, person and organisation in it is invented.

| Mock screen | Replaces | Stage |
|---|---|---|
| `Main` (Today) | `backoffice/client/pages/Attention.tsx` | 1, then 4 and 5 add to it |
| `Queue` | Nothing | 1 |
| `Palette` (⌘K) | Nothing | 1 |
| `Runbooks` | Nothing | 1 |
| `Accounts`, `Account` | `pages/Accounts.tsx` | 1 |
| `Review` (review before acting) | `shared/ui/CommandForm.tsx`, inline | 1 |
| `Orgs`, `Org` | `pages/Organisations.tsx` | 1 |
| `Trust` | `pages/Abuse.tsx` | 1, then 3 and 4 add to it |
| `Capacity` | `pages/Capacity.tsx` | 1, then 4 adds to it |
| `Jobs`, `Audit`, `Compliance` | `pages/Compliance.tsx`, split in three | 1, then 8 adds to it |
| `Access` (access and controls) | Nothing | Built, 2 |
| `Releases` | Nothing | 5 and 6 |
| `Incidents`, `IncidentRoom` | Nothing | Not decided, and 7 stands without them |
| `Phone`, `States`, `Dusk` | Not screens to build: narrow width, empty and error states, and the dusk hour, in every stage | All |

**The mock can be built as drawn.** On 2026-11-09 the twelve places where it
promised what the product cannot do were corrected in the files themselves,
so there is no longer a list to read before looking at a picture. What was
changed, and why, is in the commit that changed it; the short version:

- **Rollback is gone from every screen.** `IncidentRoom`, `Releases` and
  `Phone` now point at the runbook for reverting on `main`, and the Runbooks
  step that moved traffic is that revert. See *[Postponed](#postponed-rolling-a-release-back)*.
- **Webhooks off drops**, on `Access`, because there is no queue to hold them.
- **No screen joins an account to a network.** `Trust` and `Queue` say the
  largest network's share of a window, and count writes across every account
  created in it.
- **Nothing assumes a record nobody has decided to keep** (*[Not decided](#not-decided-the-new-records)*):
  no recorded lookups on `Accounts`, `Account`, `Audit` or `Palette`; no
  reason or reference on `Review`, `Org`, `Jobs` or an audit row; no snooze
  or mark-done on `Queue`; no review state on `Trust`; no recorded access
  review on `Access`; no "last used" on a runbook.
- **Two more the product cannot do**, found while building stage 1: `Jobs`
  offered to re-run a failed job and to cancel one, and showed a line per
  attempt. Three attempts is terminal, `cancel` only reaches a job that is
  still queued, and the document keeps a count and the last error. `Audit`
  offered a CSV export, and showed refused and failed commands — the runner
  writes the row after a command succeeds, so neither is in there.
- **Figures with no source are gone:** the 5 GB plan, the $1,500 coach
  budget, the 99.9% target, "Devices retry for 24 hours", a stored "last
  done" on the access review. Instances still show against a ceiling,
  which is `var.max_instances`.

Keep it that way: a control added to the mock that the API cannot serve is
the same bug as one added to the code.

**Redrawing it.** `roadmaps/backoffice-mock/render.mjs` draws `source/*.dc.html`
into `screens/*.png` over Playwright from ui/'s install. Edit a source, run it,
commit what it wrote — the convention `scripts/gen_icons.py` uses, and for the
same reason it has no `--check`.

## Start here

Read [docs/backoffice.md](../docs/backoffice.md) first, all of it. *The line*,
the two composition roots, one runner for every mutation, and the Atlas grant
("a command that needs another collection changes docs/backoffice.md first")
are rules every stage inherits and this file does not repeat. Then
`backoffice/README.md`, and the mock screens for your stage.

```bash
cp api/.env.operator.example api/.env.operator   # BACKOFFICE_DEV_OPERATOR stands in for IAP
cd api && just run-operator-locally              # the operator API on :7998
cd backoffice && pnpm dev                        # the page on :8081

cd api && uv run --group dev pytest src/test_operator.py src/test_operator_commands.py
cd backoffice && pnpm test && pnpm typecheck && pnpm lint
cd backoffice && pnpm gen:types                  # after any change to the operator API's schema
```

- **The look** is the bright design style with tables tighter than its usual
  spacing, and a permanent "Back office" label on every page. It is already
  applied: `backoffice/client/tokens.css`, `shared/ui/index.tsx`.
- **Commits:** code first, its tests in the next commit; frontend and backend
  never share one; one goal each. The branch is `<type>/<short-slug>`, and the
  PR body names this file and the stage.
- **A merged `terraform/` change applies on deploy, and a failed apply blocks
  every API deploy.** Watch the build. Cloud Build's account can create the new
  bindings; only the Atlas role is changed by hand.
- **When a stage ships,** delete it here and write what was built into `docs/`
  in a commit of its own ([README.md](README.md) § *When something ships*).
  Each stage names the sentence in `docs/` it overturns.

## Work

### Stage 3. Signups from one network

**Goal:** see a bulk-signup wave while it happens, and slow that one source
down, while keeping less about addresses than the request log already does. The
owner kept this and asked for it to be improved. It is the most
privacy-sensitive addition in this file.

**What exists:** Cloud Run's own request log holds each visitor's `remoteIp`
for 30 days; `routers/auth.py` limits by address, in memory, per instance
(#376); the Abuse page counts signups per day. Nothing in Beats stores an
address, and PRIVACY.md says nothing about Beats using one.

**Why stored, when the last two signals were "logged and counted, never
stored":** those are facts about one account's request, and that decision
refuses a history of what a person did. This holds no account at all. Logging
it instead would show the operator raw addresses, or need a metric label per
network, which is the unbounded cardinality that decision also refuses.

**Build:**

- **Truncate, then hash.** IPv4 to /24, IPv6 to /48, then HMAC with a key
  derived for the UTC day from a new secret, `SIGNUP_NETWORK_KEY`, held by the
  public API only. The operator can never compute a key, so it can never test a
  guess. Unset means the signal does not run, which is the self-hosted default
  (behind nginx every visitor would look like one network).
- **Store only a counter.** `signup_network_counts`: hour, opaque key, `started`,
  `completed`, and nothing else, with a 48-hour TTL index in `ensure_indexes`.
  `started` is `POST /register/start`, which **creates the user before the
  ceremony**, so user rows include abandoned starts. `completed` is a finished
  verify or an SSO account created.
- **The address** is the one `ProxyHeadersMiddleware` resolved, so a change to
  `FORWARDED_ALLOW_IPS` or a new proxy changes this signal too.
- **The read,** with named constants in `reads.py` like the others. The hour's
  completed signups against the median of the same hour of the week over the
  last eight weeks, from `users` holding a credential or an SSO identity, so
  abandoned starts do not inflate it (a baseline per network cannot exist, by
  design). Then the largest group's share of this window, shown only at or above
  a minimum group size (start at 5). Below that, nothing is shown at all.
- **The page** says "Network A", never the key. The sentence "of these accounts,
  3 have written anything" covers **every account created in the window**. It
  says, in words, that offices, universities, carrier networks and an
  organisation onboarding its staff all look like this.
- **The action** is a lower ceiling for that one key, through stage 2's control
  with the key as its subject. It slows and never blocks, and it expires at the
  next UTC midnight at the latest, because that is when the key stops matching.
  The page says so. It uses the limiter `routers/auth.py` already has.

**By hand:** the owner sets `SIGNUP_NETWORK_KEY` (a plain environment value
like the others until [secret-manager.md](secret-manager.md) lands, a fifth
secret after). Decided 2026-11-14: 32 random bytes, hex (`openssl rand -hex
32`), rotated by setting a new value — rotation only resets the day's
counters, which is harmless.

**First, in its own commit:** the sentences in PRIVACY.md and DATA.md saying what
is kept, for how long and why. Nothing ships before them. The wording,
decided 2026-11-14 and to be pasted as drafted unless the owner objects:

> To notice a burst of sign-ups from one place, LifePete keeps for 48 hours
> a count of sign-ups per hour per network, where the network is the first
> part of the visitor's address (the /24 for IPv4, the /48 for IPv6),
> hashed with a key that changes every day. The address itself is not
> stored, the hash cannot be reversed or matched against a guess after the
> day ends, and no account is ever linked to a network. The operator sees
> only how large the largest group in an hour is, and may slow sign-ups from
> it for the rest of the day; nobody is blocked.

The action is stage 2's `signups` control with the key as its subject —
stage 2 shipped, so this is unblocked.

**Tests:** IPv4 and IPv6 truncation at their boundaries; a key changing at UTC
midnight; the minimum group size holding at one below it; abandoned starts not
counted as completed. Extend `TestOperatorWall`: a planted address, whole or
truncated, appears in no operator response and no stored document.

**Done when** a scripted burst from one address shows as one network locally, a
burst below the minimum shows nothing, and the slow-down expires by itself.

**Must not:** put a network on a user document, a beat or an audit row; join an
account to a network anywhere; keep the counters past 48 hours; look
up a country or a provider; add a network label to a metric; offer a block.

**Overturns:** docs/backoffice.md § *The pages*, under *Abuse*, gains this and
the reasoning.

### Stage 4. Live health from Cloud Monitoring

**Goal:** Today and Capacity show whether the product is healthy, without opening
the Google console.

**Not blocked by [secret-manager.md](secret-manager.md).** These reads never
touch the API's Cloud Run spec.

**Build:**

- **The grant:** `roles/monitoring.viewer` on the `beats-operator` service
  account in `terraform/operator.tf`, gated on `operator_enabled` like the rest.
  It includes `monitoring.timeSeries.list` and `monitoring.alerts.list`.
- **A narrow port** in the shape of `OperatorReads`, implemented with
  `httpx.AsyncClient` and a metadata-server token, as `operator/iap.py` and
  `auth/oidc.py` make outbound calls. No Google client library: the image is
  shared with the public API.
- **`GET /api/operator/health`,** cached in the process for 30 to 60 seconds. The
  operator runs one instance, so a local cache is the whole cache. It answers
  the figures with an `as_of`. If Google fails, it answers the last figures and
  says how old they are. Locally, with no project configured, it answers
  "unavailable" and the page shows today's console link. It never shows
  invented numbers.
- **The figures:** availability (the uptime checks), share of 5xx and p95
  latency (the filters of the `api` dashboard in `terraform/monitoring.tf`, with
  a comment at both ends, since each must change with the other), instances
  against `var.max_instances` (passed in as a new env), refused writes per route
  (`write_limit_refusals`), restore sizes (`import_bytes`), and the job runner's
  last completed run.
- **Open alerts:** `GET /v3/projects/{id}/alerts`, Google's `alerts.list`.
  Google's docs marked it as public preview on 2026-11-08, so read the current
  reference first. If it has gone, link to the console as today. An alert channel
  pointing at the operator cannot work, because IAP refuses it, and a broker is
  deliberately absent.

**The availability target, decided 2026-11-14: 99.5% a month** (about 3 h
40 min of downtime), on the uptime checks of `api.lifepete.com/health` and
`lifepete.com/`. Why not 99.9%: the API is one Cloud Run service in one
region with cold starts of about 30 s, every API deploy is a revision
switch, and one person operates it; 43 minutes a month would be an error
budget spent by the first bad deploy and ignored thereafter. Why not lower:
the product holds a day job's timesheet, and a half day's outage a month is
the most the people who rely on it would call reliable. Show the budget left
in the month against it; raise it when the figures have beaten it for three
months running.

**Tests:** the parsing of Monitoring's responses (empty series, a gap, a single
point), the stale answer, and the route's auth. A fake of the port, never a
stubbed Google in a live page.

**Done when** Today and Capacity show live figures in production, and revoking
the grant turns them into a clear "old figures" state with the page still up.

**Must not:** store a time series; offer a query box; add a per-account label to
any metric; let a Google failure break a page that has other things on it.

**Overturns:** docs/backoffice.md § *The pages*, *Capacity*: "Latency, error rates
and instance counts are Cloud Monitoring's — linked, not rebuilt."

### Stage 5. Release history

**Goal:** when something breaks, see what shipped just before it.

**Build:** `GET /api/operator/releases`, cached like stage 4, and the `Releases`
screen without its rollback controls. Each row links to its commit, and a bad
one links to the runbook for reverting on `main`.

| What | From | Grant on `beats-operator` |
|---|---|---|
| API builds, newest first, with their commit | Cloud Build `builds.list` | `roles/cloudbuild.builds.viewer` |
| The API's commit | The operator's own image tag, passed in as an env. `terraform/operator.tf` gives both services `var.container_image_tag` in one apply | None |
| The web app's live commit | A `version.json` written by the build from `VITE_GIT_SHA`, fetched from `lifepete.com` | None |
| Web releases over time | Firebase Hosting's release list | `roles/firebasehosting.viewer` |
| Commit subjects | GitHub's public REST API, cached per sha for good | None; the repo is public |

- **Label the API's commit "as deployed".** If a revision failed to become
  ready, the API is still on the previous one and this figure is wrong. The
  truthful answer is the deploy-state row below, which does wait on
  [secret-manager.md](secret-manager.md).
- **A web app behind the API is normal,** because they ship separately. Show it
  as a fact and not as a problem.
- **A build viewer can read every step's arguments.** `api/cloudbuild.yaml` has no
  secrets in them today. A step that gained one would hand it to the operator.

**Tests:** merging the sources, one source failing while the others answer, a
web `version.json` that is missing.

**Done when** the screen matches production for the last ten deploys of each half.

**Must not:** add anything that moves traffic; read the API's Cloud Run service
in this stage.

### Stage 6. Deploy freeze

**Goal:** during an incident, stop a merge from shipping on top of it.

**Build:**

- **The flag is one object in a new, small, private bucket,** in Terraform, with
  `roles/storage.objectUser` for `beats-operator` on that bucket alone. **Not the
  Terraform state bucket:** the state holds `JWT_SECRET`, and the operator must
  never hold a grant there.
- **Two commands through the runner,** `deploy.freeze` (required `until`) and
  `deploy.unfreeze`, writing through a narrow port added to `CommandContext`.
  An expired flag reads as no freeze.
- **The API's check** goes in `decide` in `api/scripts/deploy_lock.sh`, which
  already holds the mutex and already skips a build that was superseded. A
  frozen build must say so in its log and skip the apply, and the lock must still
  be released. Decide whether it shows green or red, and write down why: green
  reads as "deployed".
- **After a lift, the frozen commit does not deploy by itself.** Re-run the newest
  build. The `Releases` page says which one.
- **The web app ships separately,** from the `deploy` job in
  `.github/workflows/ui.yml`, with credentials that cannot see this bucket. Either
  grant `firebase-deployer` read on it and check there, or ship API-only first
  and have the page say "the web app can still ship". Do not leave it unsaid.

**Tests:** the runner commands; `decide` with a flag, without one and with an
expired one (the script is shell, so run it with a stub `gcloud`, as far as that
is honest, and watch the first real build).

**Done when** a freeze has held back a real build, an unfreeze and re-run has
shipped it, and the lock was free afterwards.

**Must not:** put the flag anywhere the operator would need a grant on the state
bucket; allow a freeze with no end.

### Stage 7. Customer updates

Its own file, because it is not an operator feature: [status-page.md](status-page.md).

### Stage 8. Erasure request log (not urgent)

**Goal:** a request that arrives by email has a date and a visible deadline. The
owner called it nice and not urgent. PRIVACY.md promises deletion seven days
after queueing, well inside the legal month, so the risk it covers is a mail
forgotten before anything is queued.

**Build:** a small collection the operator writes through one command when the
mail arrives, holding the day it arrived, a reference and `subject_id` (never
`user_id`, or erasure's own sweep deletes it, as `MongoOperatorAudit`'s docstring
explains) and **never an address**. A request from someone with no account is a
reference alone. Attention shows any request past a named number of days with
no erasure queued. Add the collection to the Atlas grant by hand first.

Decided 2026-11-14: the collection is `erasure_requests`; the named number
of days is 14 (the PRIVACY.md promise is seven days after queueing, so a
request not queued within two weeks is the risk); a row is kept one year
after the erasure it names ran, or after it was marked closed with no
account, and the retention purge deletes it then — the same shape as the
operator audit's four years, shorter because a request names nothing but a
reference and an id.

**Must not:** add an in-app request, or keep these rows with no stated retention.

**Overturns:** docs/backoffice.md § *The pages*, *Attention*: "Erasure requests are
deliberately not counted". Its reason, that counting would take an in-app request,
does not hold for a log the operator keeps.

### Smaller items, from before the redesign

- **Before a second person is added.** PRIVACY.md's "I … am the only operator"
  sentence names them before any `viewer` goes on the allowlist, and the DPA's
  confidentiality term ([legal/dpa.md](legal/dpa.md)) says who else sees an
  organisation's members.
- **Whether the deployer keeps what it was given by hand.** Cloud Build's
  account, `cloudbuild-beats-api`, holds `roles/owner`,
  `resourcemanager.projectIamAdmin` and `serviceUsageAdmin` (read off the
  project's IAM policy on 2026-11-08), and `cloudbuild.tf` grants none of
  them, which is how CI created the operator's resources. Every push touching
  `api/**`, `terraform/**` or `backoffice/**` runs as that account, though,
  and steady-state applies only refresh what exists: once
  [secret-manager.md](secret-manager.md)'s resources and the grants in stages
  4 to 6 are created too, how much of this it keeps is the owner's call.
- **The landing page's deploy-state row** waits on
  [secret-manager.md](secret-manager.md): the API's Cloud Run spec carries
  `JWT_SECRET` and the DSN as plain environment values, so reading the
  service is reading them. Until then the Attention page links to the Cloud
  Run console. When it lands, the reads are what `deploy_lock.sh` reads —
  the API service and its revisions, the Artifact Registry tags, and
  `beats/deploy.lock` alone as an object get under a `resource.name`
  condition (a condition cannot narrow a list, so the operator never lists
  the bucket) — granted to the `beats-operator` service account.
- **A job running past the one-hour stale-claim window is reclaimed and run
  a second time, concurrently.** `claim()` cannot tell a dead run from a
  slow one, and the documented re-run safety of `organisation.delete`
  (#414) is sequential: two concurrent deletions could both read a
  project's holders before either deletes the assignments, duplicating
  hand-backs. No command comes within two orders of magnitude of an hour at
  this platform's scale, so the bound is accepted; if a purge or deletion
  ever approaches it, the runner needs a claim heartbeat (refresh
  `claimed_at` while executing) before the window is widened.
- **`subscriptions.md`** plans its seat reconciliation on the operator job
  runner; whatever that needs is its change to argue.

## Postponed: rolling a release back

The owner postponed this on 2026-11-08. A rollback stays what it is today: revert
on `main`. A build never rolls back, because `deploy_lock.sh` skips a commit the
live one already contains.

**What it would take:** `run.services.update` on the operator's service account,
which it holds nothing like today; a command through the runner; and a way to
square a moved traffic split with Terraform, whose next apply owns the service
and would move it straight back. The web app would need the same from Firebase.

**Reopen it** if a real incident shows that reverting on `main` was too slow,
measured from the merge to the live revision. Until then, no stage adds a control
that moves traffic.

## Not decided: the new records

The owner gave no answer on 2026-11-08, so **none of this is scheduled**, and no
stage may build it in passing. Each is a new thing to keep.

Since 2026-11-09 **no screen assumes any of it**: the mock was corrected rather
than left carrying controls a builder had to know to drop (§ *The design*). The
last column says what each screen does instead, which is also the thing the
decision would replace.

| Record | What it would take | What the screens do instead |
|---|---|---|
| A required reason and reference on every command | `MongoOperatorAudit.record` has no such field; only `SuspendArgs` has a reason. Add them to the `POST /commands/{name}` body rather than to each command's `args_model`, and let the runner write them | `Review` asks for the typed confirmation alone and says the record is you, the command, the subject and the two sides; `Audit` shows before and after |
| Incidents and write-ups | A new collection, its commands, and the Atlas grant | `Incidents` and `IncidentRoom` are drawn and unscheduled; stage 7 stands without them, and `Main`'s hero is the first thing on the queue |
| Restrictions in force | The list itself is derivable from `users.suspended_at` and `account_limits`, ids only, and `Trust` now shows exactly that. "Look again on" and the reference are the new part — check either against docs/backoffice.md's refusal of a browsable account list | `Trust` lists what is in force and says nothing records why, or when to look again |
| An audit of each lookup | A write on a read path, which the audit does not do today, and which a required reason would make slower to use. Needs a retention figure | `Accounts` says plainly that opening an account is a read and reads are not recorded; the recent list is ids in `localStorage`, visible to nobody else |
| Snoozing or finishing a queue item | Stored state per row, so a row can no longer simply leave when its condition clears | `Queue` says there is nothing to tick off: a row is the condition, and it leaves when the condition does |
