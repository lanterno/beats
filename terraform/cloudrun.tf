# Cloud Run service for the Beats FastAPI application
resource "google_cloud_run_service" "beats_api" {
  name     = var.api_service_name
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
          value = var.mongodb_connection_string
        }

        env {
          name  = "DB_NAME"
          value = var.mongodb_database_name
        }

        env {
          name  = "ACCESS_TOKEN"
          value = var.api_access_token
        }

        env {
          name  = "WEBAUTHN_RP_ID"
          value = var.webauthn_rp_id
        }

        env {
          name  = "WEBAUTHN_ORIGIN"
          value = var.webauthn_origin
        }

        env {
          name  = "GITHUB_CLIENT_ID"
          value = var.github_client_id
        }

        env {
          name  = "GITHUB_CLIENT_SECRET"
          value = var.github_client_secret
        }

        env {
          name  = "GITHUB_REDIRECT_URI"
          value = var.github_redirect_uri
        }

        resources {
          limits = {
            cpu    = var.cpu_limit
            memory = var.memory_limit
          }
        }
      }

      container_concurrency = var.container_concurrency
      timeout_seconds       = var.request_timeout_seconds
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
      template[0].spec[0].containers[0].image,
      template[0].metadata[0].annotations["run.googleapis.com/client-name"],
      template[0].metadata[0].annotations["run.googleapis.com/client-version"]
    ]
  }
}

# Grant Cloud Run default service account access to Artifact Registry
# Cloud Run uses the Compute Engine default service account
data "google_project" "project" {
  project_id = var.project_id
}

resource "google_artifact_registry_repository_iam_member" "cloudrun_reader" {
  project    = var.project_id
  location   = local.artifact_registry_location
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# IAM policy to allow unauthenticated access (public)
resource "google_cloud_run_service_iam_member" "public_access" {
  count    = var.allow_unauthenticated ? 1 : 0
  service  = google_cloud_run_service.beats_api.name
  location = google_cloud_run_service.beats_api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Custom domain mapping for API (api.lifepete.com)
resource "google_cloud_run_domain_mapping" "custom_domain" {
  name     = var.api_domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_service.beats_api.name
  }
}

