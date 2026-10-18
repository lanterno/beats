# Terraform Infrastructure for Beats

This Terraform configuration deploys:
- **Backend API**: FastAPI application on Cloud Run (accessible at `api.lifepete.com`)
- **DNS**: the Cloudflare records for both hostnames

It does **not** deploy the frontend. The SPA at `lifepete.com` is served by
Firebase Hosting and shipped by `.github/workflows/ui.yml` — see
[UI Deployment](#ui-deployment).

This is LifePete's one live deployment. The self-hosted stack
(`compose.selfhost.yml`) uses no cloud infrastructure at all. The repo-root
`CLAUDE.md` covers both.

## File Structure

The Terraform configuration is organized into logical modules for better maintainability:

- **`versions.tf`** - Terraform version requirements and provider versions
- **`providers.tf`** - Provider configurations (Google Cloud, Cloudflare)
- **`locals.tf`** - Local values and computed variables
- **`variables.tf`** - Input variable definitions
- **`apis.tf`** - GCP API enablement (Cloud Build, Artifact Registry, Storage, Compute)
- **`cloudbuild.tf`** - Cloud Build resources (service account, IAM, artifact registry, build triggers)
- **`cloudrun.tf`** - Cloud Run service, domain mapping, and IAM policies
- **`cloudflare.tf`** - Cloudflare DNS record management (optional)
- **`outputs.tf`** - Output values for accessing created resources

This modular structure makes it easier to:
- Find and modify specific infrastructure components
- Understand dependencies between resources
- Maintain and extend the configuration
- Review changes in version control

## GitHub Connection Setup (One-Time)

The Cloud Build trigger requires the GitHub repository to be connected to
Google Cloud Build. This is a one-time setup per repository.

The repo name is parameterized as `${var.github_owner}/${var.github_repo}`
(see [`variables.tf`](variables.tf)) — defaults to `lanterno/beats`. The
single trigger this stack defines (`${var.api_service_name}-build` in
[`cloudbuild.tf`](cloudbuild.tf)) builds the API Docker image, pushes it
to Artifact Registry, and runs `terraform apply` to deploy to Cloud Run
(one build at a time; see [How a Deploy Runs](#how-a-deploy-runs)).

The UI is **not** built by Cloud Build — it ships from GitHub Actions to
Firebase Hosting (see "UI Deployment" below). So there's only one repo to
connect.

1. **Go to Cloud Build Triggers in the GCP Console:**
   - [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers?project=beats-476914)

2. **Connect the repository:**
   - Click "Connect Repository" or "Create Trigger"
   - Select "GitHub (Cloud Build GitHub App)"
   - Authenticate with GitHub
   - Select `lanterno/beats` (or whatever `github_owner/github_repo`
     you've set in `terraform.tfvars`)
   - Click "Connect"

3. **Verify:**
   - The trigger defined in Terraform now wires up automatically.
   - The connection persists — you only do this once per repo.

**Note:** After the GitHub connection, run `terraform apply` again so the
trigger's `repo_name` reference resolves cleanly.

## How a Deploy Runs

Each build runs [`api/cloudbuild.yaml`](../api/cloudbuild.yaml): build the
image, push it tagged with the commit and `latest`, fetch `terraform.tfvars`
from Secret Manager, then deploy. Every push to `main` touching `api/**` or
`terraform/**` starts a build, so merges seconds apart run side by side. The
steps up to the tfvars fetch run in parallel across builds; **the deploy runs
one build at a time**, in three steps, with the logic in
[`api/scripts/deploy_lock.sh`](../api/scripts/deploy_lock.sh):

1. **`deploy-lock`** takes a mutex, the object
   `gs://beats-476914-terraform-state/beats/deploy.lock` (beside Terraform's
   own `default.tflock`). It is created only if absent, so one build holds it
   while the others poll every ten seconds, for up to 45 minutes. It names the
   build and commit that hold it and when they took it. A live deploy can
   hold it for nearly half an hour (five minutes of `-lock-timeout`, then the
   provider's 20-minute timeout on the Cloud Run service), so only one older
   than 40 minutes is presumed left by a build killed mid-deploy; the next
   waiter deletes it and carries on.
2. Holding the mutex, the same step reads which commit the Cloud Run service
   serves: the commit tag of its image or, when the newest revision never
   became ready and traffic stayed on an older one, the commit tag Artifact
   Registry has on that revision's image digest. It compares that commit with
   this build's in a fresh clone of the repo. If the live commit already
   contains this one, a newer build has deployed first, and this build **skips
   the apply and succeeds without deploying**; its log names the live commit.
   In every other case it applies: a newer commit, the same commit (a
   deliberate re-run re-applies the configuration), or a live image it cannot
   place (`latest`, a commit not in the repo, a digest with no single commit
   tag, no service yet).
3. **`terraform-apply`** runs `terraform apply`, or skips it as decided, and
   **`deploy-unlock`** releases the mutex, then fails the build if the apply
   failed. The release deletes the mutex only if it is still the one this
   build created.

A build fails without deploying when the guard cannot tell what to do: it
waited 45 minutes without getting the mutex, this build's commit is not in the
repo, or the service, a revision, the registry or the clone cannot be read
(each is tried three times first). It also fails when it cannot release the
mutex, so a lock left behind is never a green build.

Terraform's own state lock is not the queue. Waiting on it would hand it to
whichever build asked next, so an older build could apply after a newer one
and put the older image back. The check has to happen under a lock that also
covers the apply, which is what the mutex is. `-lock-timeout=5m` on the apply
is for a person running Terraform from a workstation at the same moment.

### A stuck deploy lock

A build that dies holding the mutex delays the next deploy by up to 40
minutes, after which the next waiting build breaks it. To clear it at once,
first check no build is deploying
(`gcloud builds list --project=beats-476914 --ongoing`):

```bash
gcloud storage cat gs://beats-476914-terraform-state/beats/deploy.lock   # who holds it
gcloud storage objects describe gs://beats-476914-terraform-state/beats/deploy.lock \
  --format='value(creation_time)'                                        # since when
gcloud storage rm gs://beats-476914-terraform-state/beats/deploy.lock
```

A build that died inside `terraform-apply` (cancelled, or stopped by the
build timeout) can also leave Terraform's own state lock,
`beats/default.tflock`, which never expires. Every later build then waits out
`-lock-timeout` and fails with "Error acquiring the state lock". Once you are
sure no apply is running, clear it from `terraform/` with
`terraform force-unlock <LOCK_ID>`; the ID is in that error, or in
`gcloud storage cat gs://beats-476914-terraform-state/beats/default.tflock`.

## Rerunning Builds

A re-run of the live commit re-applies it. A re-run of an older commit, one
the live commit already contains, succeeds without deploying: **re-running an
old build does not roll the API back.** To roll back, revert on `main`
(`git revert`, merged like any change: a new commit, which the guard
deploys), or apply a known-good image from a workstation once no build is
deploying, `terraform apply -var="container_image_tag=<good sha>"` from
`terraform/`. The next push to `main` deploys over a workstation apply.

That holds for commits that carry the guard. A build runs the
`api/cloudbuild.yaml` of its own commit, so re-running the build of a commit
from before it (AHM-92) runs the old pipeline, which applies that commit's
image whatever is live: a rollback, without a lock.

While Terraform manages the Cloud Build trigger configuration, it doesn't directly rerun builds. Here are your options:

### Option 1: Manual Trigger via gcloud CLI (Recommended)

1. Get the trigger ID from Terraform outputs:
```bash
cd terraform
terraform output cloud_build_trigger_id
```

2. Trigger the build manually:
```bash
gcloud builds triggers run <TRIGGER_ID> \
  --project=beats-476914 \
  --branch=main
```

Or use the trigger name directly:
```bash
gcloud builds triggers run beats-api-build \
  --project=beats-476914 \
  --branch=main
```

### Option 2: Push to GitHub

The trigger is configured to automatically run on pushes to the `main` branch. Simply push any commit:
```bash
git push origin main
```

**Important:** Make sure you've completed the GitHub Connection Setup (see above) before pushing. If the connection isn't established, triggers won't fire automatically.

### Option 3: View Build History

Check recent builds:
```bash
gcloud builds list --project=beats-476914 --limit=10
```

Or use the Makefile:
```bash
make build-status
```

### Option 4: View Build Logs in Terminal

**View logs for the latest build:**
```bash
make build-logs
```

**Stream logs in real-time (follow mode):**
```bash
make build-logs-follow
```

**View logs for a specific build ID:**
```bash
make build-logs-id BUILD_ID=<build-id>
# Example:
make build-logs-id BUILD_ID=7b0567e9-b97c-402b-956d-e41fc0c5d9ee
```

**Using gcloud directly:**
```bash
# Get build ID from status
BUILD_ID=$(gcloud builds list --project=beats-476914 --limit=1 --format="value(id)")

# View logs
gcloud builds log $BUILD_ID --project=beats-476914

# Stream logs (real-time)
gcloud builds log $BUILD_ID --project=beats-476914 --stream
```

### Option 5: Trigger via Cloud Console

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Find your trigger (`beats-api-build`)
3. Click "Run" → Select branch → "Run"

---

## UI Deployment

**Terraform does not deploy the UI.** It owns the API on Cloud Run and the
DNS records; the SPA is served by **Firebase Hosting**, configured in
`ui/firebase.json` and `ui/.firebaserc` (project `beats-476914`).

Deployment is automatic: the `deploy` job in `.github/workflows/ui.yml` runs
on every push to `main` that touches `ui/**`, builds with
`VITE_API_URL=https://api.lifepete.com`, and publishes to the `live` channel
using the `FIREBASE_SERVICE_ACCOUNT` secret. There is nothing to run by hand.

To publish from a workstation in an emergency:

```bash
cd ui
VITE_API_URL=https://api.lifepete.com pnpm build
npx firebase-tools deploy --only hosting
```

### DNS Configuration

- **UI Domain**: `lifepete.com` → Automatically configured via Cloudflare DNS
- **API Domain**: `api.lifepete.com` → Automatically configured via Cloudflare DNS

DNS records are automatically managed by Terraform using Cloudflare. See the Cloudflare DNS Management section below for setup instructions.

See `../ui/README.md` for more detailed deployment instructions.

## Cloudflare DNS Management

Terraform automatically manages Cloudflare DNS records for your custom domains. This eliminates the need to manually create CNAME and A records.

### Setup

1. **Create a Cloudflare API Token:**
   - Go to [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
   - Click "Create Token"
   - Use "Edit zone DNS" template or create a custom token with:
     - Permissions: `Zone.DNS:Edit`
     - Zone Resources: `Include: Specific zone: <your-zone>`
   - Copy the generated token

2. **Configure Cloudflare in Terraform:**
   Add the required variable to your `terraform.tfvars`:
   ```hcl
   cloudflare_api_token  = "your-cloudflare-api-token"
   cloudflare_zone_name  = "elghareeb.space"  # Optional: auto-detected from api_domain
   dns_proxied           = true  # Enable Cloudflare CDN/DDoS protection
   dns_ttl               = 1     # Use 1 for automatic TTL
   ```

3. **Apply the configuration:**
   ```bash
   terraform plan
   terraform apply
   ```

Terraform will automatically:
- Create a CNAME record for `api.lifepete.com` → `ghs.googlehosted.com` (Cloud Run)
- Create an A record for `lifepete.com` → Load Balancer IP address

### Configuration Options

- `cloudflare_api_token`: Your Cloudflare API token (required, sensitive)
- `cloudflare_zone_name`: Your Cloudflare zone name (optional, auto-detected from `api_domain`)
- `dns_proxied`: Enable Cloudflare proxy/CDN (default: `true`)
- `dns_ttl`: DNS record TTL in seconds (default: `1` for automatic)

### Notes

- Cloudflare DNS management is required and enabled by default
- Cloudflare proxying (`dns_proxied = true`) enables CDN, DDoS protection, and SSL
- Setting `dns_proxied = false` will expose the origin IP and may affect SSL certificate provisioning

