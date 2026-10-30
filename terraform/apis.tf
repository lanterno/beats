# Enable required GCP APIs

resource "google_project_service" "cloudbuild" {
  service = "cloudbuild.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service = "artifactregistry.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service = "storage.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service = "secretmanager.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

# Uptime checks and the dashboard (monitoring.tf).
resource "google_project_service" "monitoring" {
  service = "monitoring.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

# Log-based metrics (monitoring.tf).
resource "google_project_service" "logging" {
  service = "logging.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}
