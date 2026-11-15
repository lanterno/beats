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
