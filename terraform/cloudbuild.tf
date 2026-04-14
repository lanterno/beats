# Cloud Build Service Account
resource "google_service_account" "cloudbuild" {
  account_id   = "cloudbuild-${var.api_service_name}"
  display_name = "Cloud Build Service Account for ${var.api_service_name}"
  project      = var.project_id
}

# Grant permissions to Cloud Build service account
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

# Secret Manager — stores terraform.tfvars for CI/CD.
# Create the secret shell; you populate it manually:
#   gcloud secrets versions add beats-terraform-tfvars \
#     --data-file=terraform.tfvars --project=YOUR_PROJECT_ID
resource "google_secret_manager_secret" "terraform_tfvars" {
  secret_id = "beats-terraform-tfvars"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

# Grant Cloud Build access to read the tfvars secret
resource "google_secret_manager_secret_iam_member" "cloudbuild_secret_access" {
  secret_id = google_secret_manager_secret.terraform_tfvars.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Storage permissions for Cloud Build to read/write Terraform state bucket
resource "google_storage_bucket_iam_member" "cloudbuild_state_admin" {
  bucket = "${var.project_id}-terraform-state"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Artifact Registry permissions for Cloud Build to push images
resource "google_project_iam_member" "cloudbuild_artifactregistry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Artifact Registry repository for Docker images
resource "google_artifact_registry_repository" "docker" {
  location      = local.artifact_registry_location
  repository_id = local.artifact_registry_repo
  description   = "Docker repository for ${var.api_service_name}"
  format        = "DOCKER"
  project       = var.project_id

  depends_on = [
    google_project_service.artifactregistry,
  ]
}

# Cloud Build trigger for building and deploying the API
resource "google_cloudbuild_trigger" "docker_build" {
  name        = "${var.api_service_name}-build"
  description = "Build and deploy ${var.api_service_name} to Cloud Run"
  project     = var.project_id

  github {
    owner = var.github_owner
    name  = var.github_repo

    push {
      branch = "^${var.github_branch}$"
    }
  }

  included_files = ["api/**", "terraform/**"]
  filename       = "api/cloudbuild.yaml"

  substitutions = {
    _REGISTRY_LOCATION = local.artifact_registry_location
    _REPO_NAME         = local.artifact_registry_repo
    _IMAGE_NAME        = var.api_service_name
    _PROJECT_ID        = var.project_id
    _REGION            = var.region
  }

  service_account = google_service_account.cloudbuild.id

  depends_on = [
    google_project_service.cloudbuild,
    google_project_service.artifactregistry,
    google_artifact_registry_repository.docker,
  ]
}
