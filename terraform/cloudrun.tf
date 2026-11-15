# Cloud Run service for the Beats FastAPI application
resource "google_cloud_run_service" "beats_api" {
  name     = var.api_service_name
  location = var.region

  template {
    spec {
      # Its own account, which alone reads the four secrets below
      # (terraform/secrets.tf). Each is read by reference at `latest`, so a
      # rotation is a new version and a redeploy, never a Terraform change,
      # and no secret is in this spec, its revisions or the state.
      service_account_name = google_service_account.beats_api.email

      containers {
        image = "${local.built_image}:${var.container_image_tag}"

        ports {
          container_port = var.container_port
        }

        env {
          name = "DB_DSN"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.api["db_dsn"].secret_id
              key  = "latest"
            }
          }
        }

        env {
          name  = "DB_NAME"
          value = var.mongodb_database_name
        }

        env {
          name = "JWT_SECRET"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.api["jwt_secret"].secret_id
              key  = "latest"
            }
          }
        }

        # The proxy whose X-Forwarded-For the API believes (settings.py). Cloud
        # Run's front end reaches the container from a link-local address —
        # 169.254.169.126 on every request in the uvicorn access log — and
        # appends the visitor's address as the right-most entry, so that entry
        # is what the rate limits key on. Link-local cannot come from the
        # internet, and the whole range survives a change of address inside it.
        # Without this every visitor shares one rate-limit bucket.
        env {
          name  = "FORWARDED_ALLOW_IPS"
          value = "169.254.0.0/16"
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
          name = "ANTHROPIC_API_KEY"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.api["anthropic_api_key"].secret_id
              key  = "latest"
            }
          }
        }

        env {
          name  = "COACH_MODEL"
          value = var.coach_model
        }

        env {
          name  = "COACH_MONTHLY_BUDGET_USD"
          value = tostring(var.coach_monthly_budget_usd)
        }

        env {
          name  = "GITHUB_CLIENT_ID"
          value = var.github_client_id
        }

        env {
          name = "GITHUB_CLIENT_SECRET"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.api["github_client_secret"].secret_id
              key  = "latest"
            }
          }
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
      template[0].metadata[0].annotations["run.googleapis.com/client-name"],
      template[0].metadata[0].annotations["run.googleapis.com/client-version"]
    ]
  }

  # The grants first: a revision whose account cannot read a secret it
  # references, or pull its image, fails to deploy, and nothing else orders
  # them.
  depends_on = [
    google_secret_manager_secret_iam_member.api_reader,
    google_artifact_registry_repository_iam_member.cloudrun_reader,
  ]
}

data "google_project" "project" {
  project_id = var.project_id
}

# The API's account reads its image from the repository.
resource "google_artifact_registry_repository_iam_member" "cloudrun_reader" {
  project    = var.project_id
  location   = local.artifact_registry_location
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.beats_api.email}"
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

