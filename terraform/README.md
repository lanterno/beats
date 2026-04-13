# Terraform Infrastructure for Beats

This Terraform configuration deploys:
- **Backend API**: FastAPI application on Cloud Run (accessible at `api.lifepete.com`)
- **Frontend UI**: React static site on Cloud Storage with Load Balancer + Cloud CDN (accessible at `lifepete.com`)

## File Structure

The Terraform configuration is organized into logical modules for better maintainability:

- **`versions.tf`** - Terraform version requirements and provider versions
- **`providers.tf`** - Provider configurations (Google Cloud, Cloudflare)
- **`locals.tf`** - Local values and computed variables
- **`variables.tf`** - Input variable definitions
- **`apis.tf`** - GCP API enablement (Cloud Build, Artifact Registry, Storage, Compute)
- **`cloudbuild.tf`** - Cloud Build resources (service account, IAM, artifact registry, build triggers)
- **`cloudrun.tf`** - Cloud Run service, domain mapping, and IAM policies
- **`ui.tf`** - UI infrastructure (Cloud Storage bucket, Load Balancer, SSL certificates)
- **`cloudflare.tf`** - Cloudflare DNS record management (optional)
- **`outputs.tf`** - Output values for accessing created resources

This modular structure makes it easier to:
- Find and modify specific infrastructure components
- Understand dependencies between resources
- Maintain and extend the configuration
- Review changes in version control

## GitHub Connection Setup (One-Time)

Cloud Build triggers require your GitHub repositories to be connected to Google Cloud Build. This is a one-time setup for each repository:

### Connect API Repository (`lanterno/beats`)

1. **Go to Cloud Build Triggers in GCP Console:**
   - Navigate to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers?project=beats-476914)
   
2. **Connect Repository:**
   - Click "Connect Repository" or "Create Trigger"
   - Select "GitHub (Cloud Build GitHub App)"
   - Authenticate with GitHub
   - Select your repository: `lanterno/beats`
   - Click "Connect"

### Connect UI Repository (`lanterno/heart2`)

3. **Connect the UI Repository:**
   - Click "Connect Repository" again
   - Select "GitHub (Cloud Build GitHub App)"
   - Select your repository: `lanterno/heart2`
   - Click "Connect"

### Verify Connections

4. **Verify Connections:**
   - After connecting both repositories, the triggers defined in Terraform should automatically work
   - The connections persist - you only need to do this once per repository

**Note:** After connecting GitHub repositories, you may need to run `terraform apply` again to ensure the triggers reference the connected repositories correctly.

## Rerunning Builds

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

The UI is deployed as a static site to Google Cloud Storage with Cloud CDN.

### Initial Setup

1. **Deploy Terraform infrastructure:**
   ```bash
   cd terraform
   terraform init
   terraform plan
   terraform apply
   ```

2. **Get the Load Balancer IP:**
   ```bash
   terraform output ui_ip_address
   ```

3. **Configure DNS:**
   - Create an A record for `lifepete.com` pointing to the IP from step 2
   - SSL certificate will be automatically provisioned (takes 10-60 minutes)

4. **Deploy UI files:**
   ```bash
   cd ../ui
   pnpm run build:client
   export UI_BUCKET_NAME=$(cd ../terraform && terraform output -raw ui_bucket_name)
   ./deploy.sh
   ```

### Updating the UI

After making changes to the UI:
```bash
cd ui
pnpm run build:client
./deploy.sh
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

