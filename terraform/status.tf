# The public status file (docs/status-page.md): one JSON object in a small
# bucket of its own, read by lifepete.com/status and the SPA's banner — which
# is why it is not on Cloud Run and reads nothing from the API or Mongo: the
# page must work when the API is down. Public read for objects, GET-only CORS
# for the web origin, and the operator's grant on this bucket alone, never at
# the project level. Gated on operator_enabled like the rest of the control
# plane: without an operator nobody writes it.

resource "google_storage_bucket" "status" {
  count = var.operator_enabled ? 1 : 0

  project                     = var.project_id
  name                        = "${var.project_id}-status"
  location                    = var.region
  uniform_bucket_level_access = true
  # The one bucket that is meant to be read by anyone. The project sits in no
  # organisation, so no policy enforces prevention above this setting.
  public_access_prevention = "inherited"
  force_destroy            = true

  cors {
    origin          = [var.webauthn_origin]
    method          = ["GET"]
    response_header = ["Content-Type", "Cache-Control"]
    max_age_seconds = 3600
  }
}

resource "google_storage_bucket_iam_member" "status_public_reader" {
  count = var.operator_enabled ? 1 : 0

  bucket = google_storage_bucket.status[0].name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_iam_member" "operator_status_writer" {
  count = var.operator_enabled ? 1 : 0

  bucket = google_storage_bucket.status[0].name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.beats_operator[0].email}"
}
