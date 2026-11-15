# The API's secrets: the copies left behind

**What is blocked:** nothing. The control plane's deploy-state row waited
on the revisions from before the move, which carried the four values in the
clear; they were deleted on 2026-11-15, and the row shipped the same day
(#487; [docs/backoffice.md](../docs/backoffice.md) § *The pages*, Today).

**What blocks it:** the owner, and one API build. Deleting the old copies
cannot be undone, so the owner confirms each list; and it waits until a build
has applied with the stripped tfvars, so that until then version 8 is still
there to go back to.

Written 2026-11-04, from the control plane's review. The move itself shipped
on 2026-11-15 (#479, #485): the API reads its four secrets from Secret
Manager by reference, as a service account of its own
([terraform/README.md](../terraform/README.md) § *The API's Secrets*).

## What is true today

Since `beats-api-00182-rb5` (2026-11-15), the service's spec carries no
secret, and the 181 revisions before it, whose specs did, were deleted the
same day, and the four lines left the tfvars that evening: version 9 of
`beats-terraform-tfvars` (2026-11-15, 22:46 UTC) is the old one less those
lines, every other byte the same, and the owner's local
`terraform/terraform.tfvars` lost the same four. The values are still in the
copies made before:

- **Versions 1 to 8 of `beats-terraform-tfvars`**, all enabled. Builds read
  `latest`, so none of them is read any more.
- **The noncurrent generations of `beats/default.tfstate`** in
  `beats-476914-terraform-state`, which keeps object versions (`versioning`
  in `terraform/bootstrap/main.tf`): the 30 written before the move's apply
  (#485) finished on 2026-11-15 at 06:03 UTC.

A copy missed is still a live credential. Only rotating a secret makes every
old copy of it worthless.

## Work

1. Delete the old copies, once a build has applied with version 9:
   - **Tfvars versions 1 to 8** (`gcloud secrets versions destroy`).
   - **The state generations that still hold the values**: the noncurrent
     generations of `beats/default.tfstate` written before the move's apply
     ended. That apply wrote more than one, and one written mid-apply can
     predate the service's update, so each is checked for the plain env
     values rather than cut by time. The generations written since are the
     backups.

   Irreversible, so the owner confirms each list before it is deleted.

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
