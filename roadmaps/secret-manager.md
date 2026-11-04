# The API's secrets, out of its spec

**What is blocked:** the control plane's deploy-state row
([backoffice.md](backoffice.md) § *Attention*). That row reads the API's
service and its revisions, and can't until this lands. Nothing else waits on it.
It is still worth doing first, control plane or not: today anyone who can
describe the Cloud Run service can read every user's session key.

**What blocks it:** one question for the owner. The apply creates secrets, a
service account and IAM bindings, and nothing in the repo says Cloud Build's
account may. [backoffice.md](backoffice.md) § *Needs the owner* asks it, with
what to do for each answer; the control plane needs the same answer. A failed
apply blocks every API deploy, so it is answered before the first merge.

Written 2026-11-04, from the control plane's review.

## What is true today

`terraform/cloudrun.tf` sets four secrets as **plain environment values** on
the v1 `google_cloud_run_service`:

| Variable | Env | What it opens |
|---|---|---|
| `var.mongodb_connection_string` | `DB_DSN` | The whole database, read and write |
| `var.jwt_secret` | `JWT_SECRET` | Every user's session: anyone holding it mints a token for any account |
| `var.anthropic_api_key` | `ANTHROPIC_API_KEY` | The coach's spend |
| `var.github_client_secret` | `GITHUB_CLIENT_SECRET` | The GitHub OAuth app |

A plain value sits in three places. It is in the service's spec and in every
revision's spec, where `roles/run.viewer` reads it. It is in the Terraform
state in `beats-476914-terraform-state`. And it is in `beats-terraform-tfvars`
in Secret Manager, which Cloud Build copies into `terraform.tfvars` on every
build.

The API runs as the Compute Engine default service account (no
`service_account_name` in `cloudrun.tf`), which holds `roles/editor` on the
project.

## The shape

- **One Secret Manager secret per value**: `beats-db-dsn`, `beats-jwt-secret`,
  `beats-anthropic-api-key`, `beats-github-client-secret`. Terraform manages
  only the secret containers (`google_secret_manager_secret`) and their IAM.
  **It never manages a version.** A value goes in by hand with
  `gcloud secrets versions add`, steps in `terraform/README.md`. That takes the
  values out of the state and the tfvars as well as the spec. A
  `google_secret_manager_secret_version` fed from a tfvars variable would
  leave them in the state, which is two of the three places.
- **The service reads each one by reference**: `value_from { secret_key_ref
  { name = …, key = "latest" } }` in the v1 resource, which supports it.
  Pinning a version number instead would make a rotation a Terraform change.
  `latest` makes it a new revision, so a rotation is `versions add` followed
  by a redeploy.
- **The API gets a service account of its own** (`beats-api`), with
  `roles/secretmanager.secretAccessor` on those four secrets alone and
  `roles/artifactregistry.reader` on the repository (today's
  `cloudrun_reader` binding, moved). Not the Compute default:
  `roles/editor` doesn't read secret payloads, and granting it would hand
  them to everything else that runs as that account.
- **The variables go** from `variables.tf` in the same change that switches
  the env to references, and from the tfvars secret once that change has
  deployed (§ *Work*, step 3). Two sources for one value is how a rotation
  updates one and not the other.

## Work

1. Apply the four secret containers, then add each one's version by hand,
   with today's values. Rotating is a separate decision. Do it afterwards if
   at all, one secret at a time: rotating `JWT_SECRET` signs everyone out.
2. In one change: the service account and its bindings, the env switched to
   references, and the four variables removed from `variables.tf`. The
   service `depends_on` the bindings, so its new revision isn't made before
   its account can read what it references. That revision is the first one
   whose spec carries no secret.
3. Strip the four values from the tfvars secret **after** step 2 has
   deployed, never before. Until then `mongodb_connection_string` and
   `jwt_secret` are required variables, and one missing from the tfvars
   fails every API deploy. The other two default to an empty string, so
   their absence would quietly empty the coach's key and GitHub's. A value
   left for a variable that no longer exists only warns.
4. Delete the old copies. Moving the values stops new ones being made; the
   old ones stay where they were:
   - **Old revisions** carry them in their spec. Delete the revisions from
     before step 2 (`gcloud run revisions delete`). A rollback target is
     whatever the deploy lock allows, which today is "revert on `main`", so
     nothing is lost.
   - **The tfvars secret's earlier versions** hold them. Destroy every
     version before step 3's (`gcloud secrets versions destroy`).
   - **The state bucket keeps object versions** (`versioning` in
     `terraform/bootstrap/main.tf`), so every state written before step 2
     still holds them. Delete the noncurrent generations of
     `beats/default.tfstate` from before it. The generations written since
     are the backups.
   - **The local `terraform/terraform.tfvars`** of whoever applies by hand.

   A copy missed here is still a live credential. Only rotating a secret
   makes every old copy of it worthless.

## What must not happen

- **No secret value in Terraform**, not even as a sensitive variable. A
  sensitive variable is hidden from plan output and is still written to the
  state in the clear.
- **The control plane's service accounts get no binding on these secrets.**
  The operator deployment and its job read secrets of their own
  ([backoffice.md](backoffice.md) § *Credentials*), each bound to its own
  account. No project-level `secretAccessor` for anyone.
- **The self-hosted bundle is unaffected.** `compose.selfhost.yml` reads
  `api/.env`, and none of this touches the API's code: `Settings` reads the
  same env names whether Cloud Run fills them from a value or a reference.
