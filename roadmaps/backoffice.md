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

What follows is what the control plane still owes. Nothing left is code
waiting to be written: the first four need the owner — a console, a
credential, or a figure only production has — the fifth is a bound
accepted with the condition that would reopen it, and the last belongs to
another plan.

## Work

- **The owner turns it on.** Everything in `terraform/operator.tf` is gated
  on `operator_enabled = false` until the hand-made prerequisites exist —
  the two Atlas users and their roles, IAP's custom OAuth client and consent
  screen, the secrets' first versions, the IAM grant on the service — each
  written out in terraform/README.md. The tfvars secret
  (`beats-terraform-tfvars`) must gain the new variables **before** the flip
  merges, and the service's `run.app` URL goes into `operator_origin` after
  the first apply. PRIVACY.md's "I … am the only operator" sentence names a
  second person before any `viewer` is added to the allowlist, and the DPA's
  confidentiality term ([legal/dpa.md](legal/dpa.md)) says who else sees an
  organisation's members.
- **What Cloud Build's service account really holds.** `cloudbuild.tf`
  grants it `run.admin`, `iam.serviceAccountUser`, `logging.logWriter`, the
  tfvars secret, the state bucket and `artifactregistry.writer` — not enough
  to create service accounts, secrets, IAM bindings, enabled APIs, IAP
  settings or a scheduler job, yet the monitoring and IAM resources that
  already apply suggest more was granted by hand. Run:

  ```
  gcloud projects get-iam-policy beats-476914 \
    --flatten="bindings[].members" \
    --filter="bindings.members:cloudbuild" \
    --format="table(bindings.role)"
  ```

  If it holds `roles/editor` or more, CI applies the operator resources as it
  applies everything else; if not, the owner runs the first apply from a
  machine holding Owner, and CI's steady-state applies only refresh them —
  granting CI IAM-admin roles for a one-time creation would leave it holding
  them.
- **Turning the write-limit defaults on.** `WRITES_PER_MINUTE_BEATS`,
  `WRITES_PER_MINUTE_SIGNALS` and `IMPORTS_PER_HOUR` ship unset (no limit).
  Before one is set, check it against the per-account rate those routes
  actually see in the request logs — Cloud Monitoring has the counts per
  route, and a default that refuses a real client is a 429 storm in the
  SPA's sync engine, which retries 429. Recommended starting values (120, 60
  a minute, 10 an hour) are the comment in `api/src/beats/settings.py`.
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
