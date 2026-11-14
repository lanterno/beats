# The control plane — what is still open

The operator's control plane (#424) **shipped on 2026-11-04** and was turned
on in production on 2026-11-08. What is built, and why, is in
[docs/backoffice.md](../docs/backoffice.md), with what the public API enforces
in [docs/account-controls.md](../docs/account-controls.md) and the hand-made
prerequisites in terraform/README.md § *Operator Deployment*.

On 2026-11-08 the owner reviewed a redesign of the whole back office and
answered what it assumes but nothing provides yet. This file turns those
answers into stages that someone with no memory of the conversation can start
from. Stages 1, 2, 3, 4 and 8 — the pages reorganised around the work, the
switches with the global limits, sign-ups from one network, live health and
the erasure request log — shipped on 2026-11-14 and are in docs/backoffice.md § *The
pages* and § *Controls*; no other stage has started.

**The owner's inputs were decided on 2026-11-14**, so no stage in this file
waits on a decision; each says what was decided and why, and what is still
done by hand. Stage 7 lives in its own file and keeps its own open question.

| | Work | The owner's answer | Blocked by | Needs the owner for |
|---|---|---|---|---|
| 5 | Release history | Build | Nothing | Nothing |
| 6 | Deploy freeze | Build | Nothing | Nothing |
| 7 | Customer updates | Build | Its own file, [status-page.md](status-page.md) | The wording of the PRIVACY.md sentence |
| – | Rolling a release back from the back office | Postponed | [Below](#postponed-rolling-a-release-back) | |
| – | Reasons on commands, incidents, restrictions in force, an audit of lookups | No answer given | [Below](#not-decided-the-new-records) | The decision |

The numbers are a suggested order. Apart from what the table says, any stage
can be picked up alone. Every screen in § *The design* marked "Built" exists;
what a later stage adds to one is named in its row. Five smaller items from
before the redesign are at the end of *Work*.

**By hand, before stages 2 and 8 are used in production:** add
`platform_controls` and `erasure_requests` to the `beatsOperator` Atlas
role's writes (terraform/README.md § *Operator Deployment*). Until then
`control.set` and `erasure_request.log` fail on the write and nothing else is
affected. The limit values are set from the page, not in code: 120 beat
writes and 60 signal writes a minute and 10 imports an hour are the
recommendation, after reading the per-account rate in the request log.

**A preference for every stage left, set 2026-11-14: great defaults over new
configuration.** The goal is that LifePete is easy to start for someone new:
it may be customisable, but it should run well with nothing set beyond what it
already asks for. So a stage avoids a new environment variable, secret or
hand-made step **where it reasonably can** — this is encouraged, not a hard
rule, and a stage that genuinely needs one adds it, with a working default
where a default is possible and a sentence in its docs saying why. Stage 3
shows the preferred shape: its day key is derived from `JWT_SECRET`, which the
public API already holds, rather than from a new secret. For stages 5 and 6,
prefer what the service can learn for itself (project, region and service
name from the metadata server), have a value Terraform already knows set by
Terraform rather than by a person, and make a deployment that is not on Google
Cloud show "unavailable" and a link, never a broken page. IAM grants in
`terraform/` stay gated on `operator_enabled`, so a self-hosted install never
sees them.

## The design

**The mock** is in [backoffice-mock/](backoffice-mock/): a picture and the source
of every screen, and how to read them, with no Claude account needed. Every
figure, person and organisation in it is invented.

| Mock screen | Replaces | Stage |
|---|---|---|
| `Main` (Today) | `pages/Today.tsx` | Built, 1 and 4; 5 adds to it |
| `Queue` | `pages/Queue.tsx` | Built, 1 |
| `Palette` (⌘K) | `app/Palette.tsx` | Built, 1 |
| `Runbooks` | `pages/Runbooks.tsx` | Built, 1 |
| `Accounts`, `Account` | `pages/Accounts.tsx`, `pages/Account.tsx` | Built, 1 |
| `Review` (review before acting) | `pages/Review.tsx` | Built, 1; serves account, control and erasure-request commands |
| `Orgs`, `Org` | `pages/Organisations.tsx` | Built, 1 |
| `Trust` | `pages/Trust.tsx` | Built, 1 and 3 |
| `Capacity` | `pages/Capacity.tsx` | Built, 1 and 4 |
| `Jobs`, `Audit`, `Compliance` | `pages/Jobs.tsx`, `Audit.tsx`, `Compliance.tsx` | Built, 1 and 8 |
| `Access` (access and controls) | `pages/Access.tsx` | Built, 2 |
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

### Stage 5. Release history

**Goal:** when something breaks, see what shipped just before it.

**Build:** `GET /api/operator/releases`, cached like live health (`HealthCache` in `operator/health.py`), and the `Releases`
screen without its rollback controls. Each row links to its commit, and a bad
one links to the runbook for reverting on `main`.

| What | From | Grant on `beats-operator` |
|---|---|---|
| API builds, newest first, with their commit | Cloud Build `builds.list` | `roles/cloudbuild.builds.viewer` |
| The API's commit | The operator's own image tag, set by Terraform as an env (`terraform/operator.tf` gives both services `var.container_image_tag` in one apply), so nobody deploying sets it by hand; unset reads as "unknown" | None |
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
  5 and 6 (stage 4's `roles/monitoring.viewer` is already made) are created too, how much of this it keeps is the owner's call.
- **The landing page's deploy-state row** waits on
  [secret-manager.md](secret-manager.md): the API's Cloud Run spec carries
  `JWT_SECRET` and the DSN as plain environment values, so reading the
  service is reading them. Until then the Today page links to the Cloud
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
| Restrictions in force | The list itself is derivable from `users.suspended_at` and `account_limits`, ids only; no page lists it yet, and showing it is the cheap half. "Look again on" and the reference are the new part — check either against docs/backoffice.md's refusal of a browsable account list | Each account's page shows its own suspension and limits; nothing lists them across accounts, or records why, or when to look again |
| An audit of each lookup | A write on a read path, which the audit does not do today, and which a required reason would make slower to use. Needs a retention figure | `Accounts` says plainly that opening an account is a read and reads are not recorded; the recent list is ids in `localStorage`, visible to nobody else |
| Snoozing or finishing a queue item | Stored state per row, so a row can no longer simply leave when its condition clears | `Queue` says there is nothing to tick off: a row is the condition, and it leaves when the condition does |
