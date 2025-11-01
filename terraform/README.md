# Terraform Infrastructure for Beats API

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

