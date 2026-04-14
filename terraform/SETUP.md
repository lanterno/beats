# Terraform Setup Guide

One-time setup to enable Terraform-managed deployments with a shared GCS backend.

## Prerequisites

- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- `terraform` >= 1.10 installed
- Your GCP project ID (used throughout as `PROJECT_ID`)

## Step 1: Create the state bucket

```bash
cd terraform/bootstrap
terraform init
terraform apply -var="project_id=PROJECT_ID"
```

This creates a GCS bucket named `PROJECT_ID-terraform-state` with versioning.

## Step 2: Update the backend config

Edit `terraform/versions.tf` and replace the placeholder in the backend block:

```hcl
backend "gcs" {
  bucket = "PROJECT_ID-terraform-state"  # <-- your actual project ID
  prefix = "beats"
}
```

## Step 3: Initialize and migrate state

```bash
cd terraform
terraform init -migrate-state
```

If you had existing local state, Terraform will ask to copy it to GCS. Say yes.

## Step 4: Create your terraform.tfvars

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your actual values
```

## Step 5: Apply

```bash
terraform apply
```

This sets up all infrastructure including the Secret Manager secret for CI.

## Step 6: Upload tfvars to Secret Manager (for CI/CD)

Cloud Build needs the same variable values. Upload your tfvars as a secret:

```bash
gcloud secrets versions add beats-terraform-tfvars \
  --data-file=terraform.tfvars \
  --project=PROJECT_ID
```

**Important:** Re-run this command whenever you change `terraform.tfvars`.

## How CI/CD works

On every push to `main` that changes `api/**` or `terraform/**`:

1. Cloud Build builds and pushes the Docker image (tagged with commit SHA)
2. Cloud Build fetches `terraform.tfvars` from Secret Manager
3. Cloud Build runs `terraform apply -var="container_image_tag=$COMMIT_SHA"`
4. Terraform updates the Cloud Run service with the new image and all env vars

Local `terraform apply` and CI/CD share the same GCS state — no conflicts.

## Updating environment variables

1. Edit your local `terraform.tfvars`
2. Run `terraform apply` locally
3. Re-upload tfvars to Secret Manager:
   ```bash
   gcloud secrets versions add beats-terraform-tfvars \
     --data-file=terraform.tfvars --project=PROJECT_ID
   ```

This ensures the next CI deploy uses the same values.
