# The operator deployment (roadmaps/backoffice.md step 2): the same API image
# running `operator_server:app`, behind Cloud Run's own IAP — no load
# balancer, by decision (about $18 a month standing buys one person nothing).
#
# Everything here is gated on var.operator_enabled, default false, because the
# service cannot become ready before three things are made **by hand** (the
# README's "Operator deployment" section): the custom OAuth client IAP needs
# in a project with no organisation, the narrow Atlas database user, and the
# secret's first version. Flip the variable after those exist; until then an
# apply changes nothing and the API's deploy stays green.

resource "google_service_account" "beats_operator" {
  count = var.operator_enabled ? 1 : 0

  project      = var.project_id
  account_id   = "beats-operator"
  display_name = "The operator deployment (beats-operator)"
  description  = "Runs the control plane. Never the Compute Engine default, which holds roles/editor and reads the whole state bucket."
}

# The container: its value — the narrow Atlas user's DSN — is added by hand
# with `gcloud secrets versions add` and never passes through Terraform, which
# manages the container and the binding only (roadmaps/secret-manager.md
# § The shape, for the same reason).
resource "google_secret_manager_secret" "beats_operator_dsn" {
  count = var.operator_enabled ? 1 : 0

  project   = var.project_id
  secret_id = "beats-operator-dsn"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_iam_member" "operator_dsn_reader" {
  count = var.operator_enabled ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.beats_operator_dsn[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.beats_operator[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "operator_image_reader" {
  count = var.operator_enabled ? 1 : 0

  project    = var.project_id
  location   = local.artifact_registry_location
  repository = local.artifact_registry_repo
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.beats_operator[0].email}"
}

resource "google_project_service" "iap" {
  count = var.operator_enabled ? 1 : 0

  service            = "iap.googleapis.com"
  project            = var.project_id
  disable_on_destroy = false
}

resource "google_cloud_run_v2_service" "beats_operator" {
  count = var.operator_enabled ? 1 : 0

  project  = var.project_id
  name     = var.operator_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  # Cloud Run's built-in IAP — works for a project in no Google Cloud
  # organisation through the hand-made OAuth client. A GA argument of
  # hashicorp/google on ~> 8.8 (confirmed against the roadmap's check).
  iap_enabled = true

  template {
    service_account = google_service_account.beats_operator[0].email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      # The API's image, verbatim; only the command differs. A bare `python`
      # in the image is the system interpreter without the project's
      # dependencies, hence uv.
      image   = "${local.built_image}:${var.container_image_tag}"
      command = ["uv"]
      args = [
        "run", "--no-dev", "uvicorn", "operator_server:app",
        "--host", "0.0.0.0", "--port", "8080",
        "--app-dir", "src", "--no-proxy-headers",
      ]

      ports {
        container_port = 8080
      }

      env {
        name = "OPERATOR_DB_DSN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.beats_operator_dsn[0].secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "OPERATOR_DB_NAME"
        value = var.mongodb_database_name
      }

      # The assertion's `aud`: the project number, not its id.
      env {
        name  = "OPERATOR_IAP_AUDIENCE"
        value = "/projects/${data.google_project.project.number}/locations/${var.region}/services/${var.operator_service_name}"
      }

      env {
        name  = "OPERATOR_ALLOWLIST"
        value = var.operator_allowlist
      }

      # The run.app URL, known only after the first apply: create, read the
      # URL off the service, set the tfvar, apply again. Until then every
      # write answers 403 OPERATOR_BAD_ORIGIN, which fails closed.
      env {
        name  = "OPERATOR_ORIGIN"
        value = var.operator_origin
      }

      # Mirrors the API's setting so the landing page's "near the cap" and
      # the account page's bar mean what the API enforces.
      env {
        name  = "COACH_MONTHLY_BUDGET_USD"
        value = tostring(var.coach_monthly_budget_usd)
      }
    }
  }

  depends_on = [google_project_service.iap]
}

# IAP's service agent is the only invoker: no allUsers, and nothing reaches
# the container but what IAP has already authenticated.
resource "google_cloud_run_v2_service_iam_member" "operator_iap_invoker" {
  count = var.operator_enabled ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.beats_operator[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

# A 5xx alert in the shape of api_5xx (alerts.tf): the operator service is
# opened rarely, so a broken revision would otherwise sit unnoticed.
resource "google_monitoring_alert_policy" "operator_5xx" {
  count = var.operator_enabled ? 1 : 0

  display_name          = "${var.operator_service_name}: more than 2% of requests answered 5xx"
  project               = var.project_id
  combiner              = "AND"
  severity              = "ERROR"
  notification_channels = local.alert_channels

  conditions {
    display_name = "5xx share of requests over 5 minutes above 2%"

    condition_threshold {
      filter             = "${local.operator_metrics} AND metric.type=\"run.googleapis.com/request_count\" AND metric.label.response_code_class=\"5xx\""
      denominator_filter = "${local.operator_metrics} AND metric.type=\"run.googleapis.com/request_count\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      denominator_aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 0.02
      duration        = "0s"

      trigger {
        count = 1
      }
    }
  }
}

locals {
  operator_metrics = "resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"${var.operator_service_name}\""
}
