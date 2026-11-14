# The public status file (docs/status-page.md): one JSON object in a small
# bucket of its own, read by lifepete.com/status and the SPA's banner — which
# is why it is not on Cloud Run and reads nothing from the API or Mongo: the
# page must work when the API is down. Public read for objects, GET-only CORS
# for any origin, and the operator's grant on this bucket alone, never at the
# project level. Gated on operator_enabled like the rest of the control
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

  # Any origin, decided 2026-11-14. The file is public to everyone already
  # (status_public_reader below) and the browser sends no credential for it,
  # so naming origins hides nothing; it would only decide which copies of the
  # SPA may show the banner. The same build is served at lifepete.com and at
  # Firebase's own hosts for the site, and a dev server can be pointed at the
  # file: listing one origin left those with a CORS error instead of a status.
  cors {
    origin          = ["*"]
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
