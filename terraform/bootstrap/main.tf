# Bootstrap — run once to create the GCS bucket for Terraform remote state.
#
# Usage:
#   cd terraform/bootstrap
#   terraform init
#   terraform apply -var="project_id=YOUR_PROJECT_ID"
#
# After this succeeds, go back to terraform/ and run:
#   terraform init -migrate-state
#
# This migrates your local state to the new GCS backend.

terraform {
  required_version = ">= 1.10"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.9"
    }
  }
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the bucket"
  type        = string
  default     = "us-central1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_storage_bucket" "terraform_state" {
  name     = "${var.project_id}-terraform-state"
  location = var.region
  project  = var.project_id

  # Prevent accidental deletion
  force_destroy = false

  versioning {
    enabled = true
  }

  # Clean up old state versions after 30 days
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5
    }
  }

  uniform_bucket_level_access = true
}

output "bucket_name" {
  value = google_storage_bucket.terraform_state.name
}
