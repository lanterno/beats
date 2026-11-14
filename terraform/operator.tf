# The operator deployment (docs/backoffice.md step 2): the same API image
# running `operator_server:app`, behind Cloud Run's own IAP — no load
# balancer, by decision (about $18 a month standing buys one person nothing).
#
# Everything here but the two secret containers is gated on
# var.operator_enabled, default false, because the service cannot become ready
# before its prerequisites are made **by hand** (the README's "Operator
# Deployment" section): the custom OAuth client IAP needs in a project with no
# organisation, the two Atlas database users, and each secret's first version.
# The containers stand outside the flag because a first version needs a
# container to go in, and an empty one costs nothing and opens nothing. Flip
# the variable after the versions exist; until then an apply changes nothing
# else and the API's deploy stays green.

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
  secret_id = google_secret_manager_secret.beats_operator_dsn.secret_id
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
            secret  = google_secret_manager_secret.beats_operator_dsn.secret_id
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

      # The one origin writes are accepted from: its own hostname. The run.app
      # URL stays up behind the same IAP, and a write from it answers 403
      # OPERATOR_BAD_ORIGIN.
      env {
        name  = "OPERATOR_ORIGIN"
        value = "https://${var.operator_domain}"
      }

      # Mirrors the API's setting so the landing page's "near the cap" and
      # the account page's bar mean what the API enforces.
      env {
        name  = "COACH_MONTHLY_BUDGET_USD"
        value = tostring(var.coach_monthly_budget_usd)
      }

      # Live health (api/src/beats/operator/health.py): which service's
      # figures to read, and the ceiling its instances are drawn against.
      # The project and the token come from the metadata server.
      env {
        name  = "OPERATOR_API_SERVICE"
        value = var.api_service_name
      }

      env {
        name  = "OPERATOR_API_MAX_INSTANCES"
        value = tostring(var.max_instances)
      }

      # Release history (api/src/beats/operator/releases.py): the commit both
      # services were deployed with in this apply, and where the web app's
      # version.json is served.
      env {
        name  = "OPERATOR_API_COMMIT"
        value = var.container_image_tag
      }

      env {
        name  = "OPERATOR_WEB_ORIGIN"
        value = var.webauthn_origin
      }

      # The deploy freeze's bucket (api/src/beats/operator/deploy_freeze.py).
      env {
        name  = "OPERATOR_FREEZE_BUCKET"
        value = google_storage_bucket.deploy_freeze[0].name
      }

      # The public status file's bucket (api/src/beats/operator/status_page.py).
      env {
        name  = "OPERATOR_STATUS_BUCKET"
        value = google_storage_bucket.status[0].name
      }
    }
  }

  # The grant first: a revision whose account cannot read its secret fails to
  # deploy, and nothing else orders the two.
  depends_on = [
    google_project_service.iap,
    google_secret_manager_secret_iam_member.operator_dsn_reader,
  ]
}

# Live health: reading time series and alert policies, nothing else. The
# viewer role writes nothing and reads no log entry or secret.
resource "google_project_iam_member" "operator_monitoring_viewer" {
  count = var.operator_enabled ? 1 : 0

  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.beats_operator[0].email}"
}

# Release history: Cloud Build's build list, read-only. A build viewer can
# read every step's arguments, so api/cloudbuild.yaml must never put a secret
# in one.
resource "google_project_iam_member" "operator_build_viewer" {
  count = var.operator_enabled ? 1 : 0

  project = var.project_id
  role    = "roles/cloudbuild.builds.viewer"
  member  = "serviceAccount:${google_service_account.beats_operator[0].email}"
}

# The deploy freeze: one flag object in a small private bucket of its own —
# never the Terraform state bucket, which holds JWT_SECRET. The operator writes
# it; the API's build reads it in deploy_lock.sh's decide. Its name is fixed
# because api/cloudbuild.yaml names it too.
resource "google_storage_bucket" "deploy_freeze" {
  count = var.operator_enabled ? 1 : 0

  project                     = var.project_id
  name                        = "${var.project_id}-deploy-freeze"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true
}

resource "google_storage_bucket_iam_member" "operator_freeze_writer" {
  count = var.operator_enabled ? 1 : 0

  bucket = google_storage_bucket.deploy_freeze[0].name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.beats_operator[0].email}"
}

resource "google_storage_bucket_iam_member" "cloudbuild_freeze_reader" {
  count = var.operator_enabled ? 1 : 0

  bucket = google_storage_bucket.deploy_freeze[0].name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloudbuild.email}"
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

# The back office's hostname, as api.lifepete.com is the API's. Google lets only
# a verified owner of the domain create a mapping, and every one in this project
# was created by the owner's own account, so this one was too, then imported.
resource "google_cloud_run_domain_mapping" "operator" {
  count = var.operator_enabled ? 1 : 0

  name     = var.operator_domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.beats_operator[0].name
  }
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

# ── The job runner (docs/backoffice.md step 4) ───────────────────────────
#
# A Cloud Run Job running `python -m beats.operator.jobs`, started by Cloud
# Scheduler every 15 minutes. It finds nothing due and exits on almost every
# run, which on Cloud Run Jobs costs next to nothing. Nothing else is
# scheduled: the retention purge stays an act the operator starts (decision
# 30), now from a page rather than a shell.

resource "google_project_service" "cloudscheduler" {
  count = var.operator_enabled ? 1 : 0

  service            = "cloudscheduler.googleapis.com"
  project            = var.project_id
  disable_on_destroy = false
}

resource "google_service_account" "beats_operator_jobs" {
  count = var.operator_enabled ? 1 : 0

  project      = var.project_id
  account_id   = "beats-operator-jobs"
  display_name = "The operator job runner (beats-operator-jobs)"
  description  = "Runs the queued irreversible work. A database user of its own, so each credential rotates alone and the operator's stays narrow."
}

resource "google_secret_manager_secret" "beats_jobs_dsn" {
  project   = var.project_id
  secret_id = "beats-jobs-dsn"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_iam_member" "jobs_dsn_reader" {
  count = var.operator_enabled ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.beats_jobs_dsn.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.beats_operator_jobs[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "jobs_image_reader" {
  count = var.operator_enabled ? 1 : 0

  project    = var.project_id
  location   = local.artifact_registry_location
  repository = local.artifact_registry_repo
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.beats_operator_jobs[0].email}"
}

resource "google_cloud_run_v2_job" "beats_operator_jobs" {
  count = var.operator_enabled ? 1 : 0

  project  = var.project_id
  name     = "beats-operator-jobs"
  location = var.region

  template {
    template {
      service_account = google_service_account.beats_operator_jobs[0].email
      max_retries     = 0 # the queue retries to its own attempt cap

      containers {
        image = "${local.built_image}:${var.container_image_tag}"
        # A bare `python` in the image is the system interpreter without the
        # project's dependencies, hence uv; PYTHONPATH because the module
        # lives under src/.
        command = ["uv"]
        args    = ["run", "--no-dev", "python", "-m", "beats.operator.jobs"]

        env {
          name  = "PYTHONPATH"
          value = "src"
        }

        env {
          name = "OPERATOR_JOBS_DB_DSN"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.beats_jobs_dsn.secret_id
              version = "latest"
            }
          }
        }

        env {
          name  = "OPERATOR_JOBS_DB_NAME"
          value = var.mongodb_database_name
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.jobs_dsn_reader]
}

resource "google_service_account" "beats_operator_scheduler" {
  count = var.operator_enabled ? 1 : 0

  project      = var.project_id
  account_id   = "beats-operator-scheduler"
  display_name = "Starts beats-operator-jobs on its tick"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invokes_jobs" {
  count = var.operator_enabled ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.beats_operator_jobs[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.beats_operator_scheduler[0].email}"
}

resource "google_cloud_scheduler_job" "operator_jobs_tick" {
  count = var.operator_enabled ? 1 : 0

  project   = var.project_id
  region    = var.region
  name      = "beats-operator-jobs-tick"
  schedule  = "*/15 * * * *"
  time_zone = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.beats_operator_jobs[0].name}:run"

    oauth_token {
      service_account_email = google_service_account.beats_operator_scheduler[0].email
    }
  }

  depends_on = [google_project_service.cloudscheduler]
}

# A failing job logs at ERROR (beats/operator/jobs.py) — a silently failing
# erasure must page somebody. Every other alert watches only beats-api.
resource "google_logging_metric" "operator_job_failures" {
  count = var.operator_enabled ? 1 : 0

  project = var.project_id
  name    = "operator-job-failures"
  filter  = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"beats-operator-jobs\" AND severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "operator_job_failed" {
  count = var.operator_enabled ? 1 : 0

  display_name          = "beats-operator-jobs: a queued job failed"
  project               = var.project_id
  combiner              = "OR"
  severity              = "ERROR"
  notification_channels = local.alert_channels

  conditions {
    display_name = "More than zero job errors in 15 minutes"

    condition_threshold {
      filter = "resource.type=\"cloud_run_job\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.operator_job_failures[0].name}\""

      aggregations {
        alignment_period   = "900s"
        per_series_aligner = "ALIGN_SUM"
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      trigger {
        count = 1
      }
    }
  }
}
