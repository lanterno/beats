# The API's secrets: the copies left behind

**What is blocked:** nothing. The control plane's deploy-state row (step 3)
waited on the revisions from before the move, which carried the four values
in the clear; they were deleted on 2026-11-15.

**What blocks it:** the owner, for steps 1 and 2. Step 1 writes a new
version of the tfvars secret and step 2 deletes for good, and both are the
owner's to run: an agent's attempt to copy these values was refused by its
permission check, which is the right place for that line to be, and step 2
cannot be undone.

Written 2026-11-04, from the control plane's review. The move itself shipped
on 2026-11-15 (#479, #485): the API reads its four secrets from Secret
Manager by reference, as a service account of its own
([terraform/README.md](../terraform/README.md) § *The API's Secrets*).

## What is true today

Since `beats-api-00182-rb5` (2026-11-15), the service's spec carries no
secret, and the 181 revisions before it, whose specs did, were deleted the
same day. The values are still in the other copies made before it:

- **Every version of `beats-terraform-tfvars`** (8, all enabled), the latest
  among them. Cloud Build still copies it into `terraform.tfvars` on every
  build; nothing declares the four variables any more, so they only warn.
- **The noncurrent generations of `beats/default.tfstate`** in
  `beats-476914-terraform-state`, which keeps object versions (`versioning`
  in `terraform/bootstrap/main.tf`): 30 of them, every one written before
  step 2's apply finished on 2026-11-15 at 06:03 UTC.
- **The local `terraform/terraform.tfvars`** of whoever applies by hand.

A copy missed is still a live credential. Only rotating a secret makes every
old copy of it worthless.

## Work

1. Strip the four values from the tfvars secret: a new version of
   `beats-terraform-tfvars` without `mongodb_connection_string`, `jwt_secret`,
   `anthropic_api_key` and `github_client_secret`, every other line
   byte-identical. Safe now that nothing declares them; before 2026-11-15 a
   missing `jwt_secret` would have failed every API deploy. The local
   `terraform.tfvars` loses the same four lines.
2. Delete the old copies, once step 1 has a build behind it:
   - **Every tfvars version before step 1's**
     (`gcloud secrets versions destroy`).
   - **The state generations that still hold the values**: the noncurrent
     generations of `beats/default.tfstate` written before step 2's apply
     ended. Step 2's apply wrote more than one, and one written mid-apply can
     predate the service's update, so each is checked for the plain env
     values rather than cut by time. The generations written since are the
     backups.

   Irreversible, so the owner confirms each list before it is deleted.
3. **Then the control plane's deploy-state row** (moved here from the
   control plane's roadmap on 2026-11-14, when the rest of it shipped): with
   no revision's spec carrying a secret, reading the service is safe, and
   Today can say whether the newest revision became ready instead of linking
   to the Cloud Run console. Nothing blocks it since the old revisions
   went. The reads are what `api/scripts/deploy_lock.sh`
   reads — the API service and its revisions, the Artifact Registry tags,
   and `beats/deploy.lock` alone as an object get under a `resource.name`
   condition (a condition cannot narrow a list, so the operator never lists
   the state bucket) — granted to the `beats-operator` service account in
   `terraform/operator.tf`, gated on `operator_enabled`. The Releases page's
   "as deployed" label on the API's commit goes then, replaced by the truth.

## What must not happen

- **No secret value in Terraform**, not even as a sensitive variable. A
  sensitive variable is hidden from plan output and is still written to the
  state in the clear.
- **The control plane's service accounts get no binding on these secrets.**
  The operator deployment and its job read secrets of their own
  ([docs/backoffice.md](../docs/backoffice.md) § *Deployment*), each bound to its own
  account. No project-level `secretAccessor` for anyone.
- **The self-hosted bundle is unaffected.** `compose.selfhost.yml` reads
  `api/.env`, and none of this touches the API's code: `Settings` reads the
  same env names whether Cloud Run fills them from a value or a reference.
