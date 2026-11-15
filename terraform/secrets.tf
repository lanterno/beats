# The API's four secrets, each in a Secret Manager secret of its own
# (roadmaps/secret-manager.md). Terraform manages the containers only, never a
# version: a value is added by hand with `gcloud secrets versions add` (the
# README's "The API's Secrets"), so it is in no plan, no state and no tfvars.
# A google_secret_manager_secret_version fed from a variable would put it back
# in the state, which is two of the three places this is moving it out of.

locals {
  api_secrets = {
    db_dsn               = "beats-db-dsn"
    jwt_secret           = "beats-jwt-secret"
    anthropic_api_key    = "beats-anthropic-api-key"
    github_client_secret = "beats-github-client-secret"
  }
}

resource "google_secret_manager_secret" "api" {
  for_each = local.api_secrets

  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

# The API runs as an account of its own, not the Compute Engine default, which
# holds roles/editor: editor does not read secret payloads, and granting the
# default this would hand the secrets to everything else that runs as it. The
# API calls no Google API at runtime (the operator code that does runs under
# beats-operator), so this account reads its four secrets and its image, and
# nothing else.
resource "google_service_account" "beats_api" {
  project      = var.project_id
  account_id   = "beats-api"
  display_name = "The API (beats-api)"
  description  = "Runs the public API. Reads its four secrets and its image; never the Compute Engine default."
}

# Each secret to this account alone: no project-level secretAccessor, and no
# binding for the control plane's accounts, which read secrets of their own.
resource "google_secret_manager_secret_iam_member" "api_reader" {
  for_each = google_secret_manager_secret.api

  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.beats_api.email}"
}
