# The control plane — what is still open

The operator's control plane (#424) **shipped on 2026-11-04**: the four steps
the plan here used to carry — enforcement in the public API, the read-only
operator deployment, the inline commands, the job queue and the irreversible
work — are built, and their design moved where built things live:

- [docs/account-controls.md](../docs/account-controls.md) — suspension,
  sign-out everywhere, the day last seen, per-account limits, and what each
  client does with a refusal;
- [docs/backoffice.md](../docs/backoffice.md) — the line, the two composition
  roots, the commands and the runner, the jobs, authentication, deployment
  and the pages;
- terraform/README.md § *Operator Deployment* — the hand-made prerequisites.

The two abuse signals that had no data source were settled on 2026-11-07:
both are logged and counted, never stored, and their pages link to the
query — the reasoning is in [docs/backoffice.md](../docs/backoffice.md)
§ *The pages* under *Abuse*.

What follows is what the control plane still owes. The first three need
the owner — a console, a decision, or a figure only production has — the
fourth waits on [secret-manager.md](secret-manager.md), the fifth is a bound
accepted with the condition that would reopen it, and the last belongs to
another plan.

## Work

- **The owner turns it on.** All of `terraform/operator.tf` but the two
  empty secret containers is gated on `operator_enabled = false` until the
  hand-made prerequisites exist — the two Atlas users and their roles, IAP's
  custom OAuth client and consent screen, the secrets' first versions, IAP's
  service agent — each written out in terraform/README.md, with what follows
  the first apply: the client attached, the IAM grant on the service, the
  `run.app` URL in `operator_origin`. The first apply has never been
  rehearsed, and neither `validate` nor `plan` can show whether Google accepts
  `iap_enabled` on a service with no OAuth client attached yet, so the build
  is watched, and if it fails the flag comes back out of the tfvars secret.
  PRIVACY.md's "I … am the only operator" sentence names a second person
  before any `viewer` is added to the allowlist, and the DPA's confidentiality
  term ([legal/dpa.md](legal/dpa.md)) says who else sees an organisation's
  members.
- **Whether the deployer keeps what it was given by hand.** Cloud Build's
  account, `cloudbuild-beats-api`, holds `roles/owner`,
  `resourcemanager.projectIamAdmin` and `serviceUsageAdmin` (read off the
  project's IAM policy on 2026-11-08), and `cloudbuild.tf` grants none of
  them. So CI applies the operator resources as it applies everything else,
  and no first apply from another machine is needed. Every push touching
  `api/**`, `terraform/**` or `backoffice/**` runs as that account, though,
  and steady-state applies only refresh what exists: once the operator's and
  [secret-manager.md](secret-manager.md)'s resources are created, how much of
  this it keeps is the owner's call.
- **Turning the write-limit defaults on.** `WRITES_PER_MINUTE_BEATS`,
  `WRITES_PER_MINUTE_SIGNALS` and `IMPORTS_PER_HOUR` ship unset (no limit).
  Before one is set, check it against the per-account rate those routes
  actually see in the request logs — Cloud Monitoring has the counts per
  route, and a default that refuses a real client is a 429 storm in the
  SPA's sync engine, which retries 429. Recommended starting values (120, 60
  a minute, 10 an hour) are the comment in `api/src/beats/settings.py`.
  `terraform/cloudrun.tf` does not pass them to the service yet, so the first
  one set is also a Terraform change.
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
