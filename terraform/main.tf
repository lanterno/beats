terraform {
  required_version = ">= 1.10"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.9"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  # Use Artifact Registry instead of GCR
  artifact_registry_location = "europe"
  artifact_registry_repo      = "docker"
  
  # Build image URL for Artifact Registry
  built_image = "${local.artifact_registry_location}-docker.pkg.dev/${var.project_id}/${local.artifact_registry_repo}/${var.service_name}"
}

# Enable required APIs
resource "google_project_service" "cloudbuild" {
  service = "cloudbuild.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

# Enable Artifact Registry API
resource "google_project_service" "artifactregistry" {
  service = "artifactregistry.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

# Service account for Cloud Build
resource "google_service_account" "cloudbuild" {
  account_id   = "cloudbuild-${var.service_name}"
  display_name = "Cloud Build Service Account for ${var.service_name}"
  project      = var.project_id
}

# Grant permissions to Cloud Build service account
resource "google_project_iam_member" "cloudbuild_storage" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_service_account_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_artifactregistry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_artifactregistry_admin" {
  project = var.project_id
  role    = "roles/artifactregistry.admin"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Artifact Registry repository for Docker images
resource "google_artifact_registry_repository" "docker" {
  location      = local.artifact_registry_location
  repository_id = local.artifact_registry_repo
  description   = "Docker repository for ${var.service_name}"
  format        = "DOCKER"
  project       = var.project_id

  depends_on = [
    google_project_service.artifactregistry,
  ]
}

# Cloud Build trigger for building Docker images
resource "google_cloudbuild_trigger" "docker_build" {
  name        = "${var.service_name}-build"
  description = "Build and push Docker image for ${var.service_name}"
  project     = var.project_id

  github {
    owner = var.github_owner
    name  = var.github_repo

    push {
      branch = "^${var.github_branch}$"
    }
  }

  filename = "cloudbuild.yaml"

  substitutions = {
    _REGISTRY_LOCATION = local.artifact_registry_location
    _REPO_NAME         = local.artifact_registry_repo
    _IMAGE_NAME        = var.service_name
    _PROJECT_ID        = var.project_id
  }

  service_account = google_service_account.cloudbuild.id

  depends_on = [
    google_project_service.cloudbuild,
    google_project_service.artifactregistry,
    google_artifact_registry_repository.docker,
  ]
}

# Cloud Run service for the Beats FastAPI application
resource "google_cloud_run_service" "beats_api" {
  name     = var.service_name
  location = var.region

  template {
    spec {
      containers {
        image = "${local.built_image}:latest"
        
        ports {
          container_port = var.container_port
        }
        
        env {
          name  = "DB_DSN"
          value = var.db_dsn
        }
        
        env {
          name  = "DB_NAME"
          value = var.db_name
        }
        
        env {
          name  = "ACCESS_TOKEN"
          value = var.access_token
        }
        
        resources {
          limits = {
            cpu    = var.cpu_limit
            memory = var.memory_limit
          }
        }
      }
      
      container_concurrency = var.container_concurrency
      timeout_seconds      = var.timeout_seconds
    }
    
    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = tostring(var.min_instances)
        "autoscaling.knative.dev/maxScale" = tostring(var.max_instances)
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  lifecycle {
    ignore_changes = [
      template[0].spec[0].containers[0].image
    ]
  }
}

# IAM policy to allow unauthenticated access (public)
resource "google_cloud_run_service_iam_member" "public_access" {
  count    = var.allow_unauthenticated ? 1 : 0
  service  = google_cloud_run_service.beats_api.name
  location = google_cloud_run_service.beats_api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Custom domain mapping
resource "google_cloud_run_domain_mapping" "custom_domain" {
  name     = var.custom_domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_service.beats_api.name
  }
}
