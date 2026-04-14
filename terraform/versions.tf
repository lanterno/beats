terraform {
  required_version = ">= 1.10"

  # Remote state in GCS — shared between local and CI/CD.
  # The bucket is created by terraform/bootstrap/.
  # Replace PROJECT_ID with your actual GCP project ID, then run:
  #   terraform init -migrate-state
  backend "gcs" {
    bucket = "beats-476914-terraform-state"
    prefix = "beats"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.9"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}
