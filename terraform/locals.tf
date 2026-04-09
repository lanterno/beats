locals {
  artifact_registry_location = "europe-west1"
  artifact_registry_repo     = "docker"

  # Docker image URL in Artifact Registry
  built_image = "${local.artifact_registry_location}-docker.pkg.dev/${var.project_id}/${local.artifact_registry_repo}/${var.api_service_name}"
}
