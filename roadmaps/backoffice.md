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

What follows is what the control plane still owes.

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
- **Two abuse signals have no data source yet.** The design wanted "accounts
  refused 429 on a write route in the last seven days" on the Attention page
  and import sizes on the Abuse page; nothing records either — slowapi
  counts in memory, and the import route keeps no size. Each needs the API
  to write a small record first (a counter document, or a log-based metric
  the page links to instead), which is its own decision about what to keep,
  not a page to add.
- **`subscriptions.md`** plans its seat reconciliation on the operator job
  runner; whatever that needs is its change to argue.
