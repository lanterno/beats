output "service_url" {
  description = "Public URL of the deployed Cloud Run service"
  value       = google_cloud_run_service.beats_api.status[0].url
}

output "service_name" {
  description = "Name of the deployed Cloud Run service"
  value       = google_cloud_run_service.beats_api.name
}

output "service_location" {
  description = "Region where the service is deployed"
  value       = google_cloud_run_service.beats_api.location
}

output "dashboard_url" {
  description = "GCP Console URL to view the service"
  value       = "https://console.cloud.google.com/run/detail/${var.region}/${google_cloud_run_service.beats_api.name}?project=${var.project_id}"
}

output "custom_domain_url" {
  description = "Custom domain URL"
  value       = "https://${var.custom_domain}"
}

output "cloud_build_trigger_id" {
  description = "Cloud Build trigger ID"
  value       = google_cloudbuild_trigger.docker_build.trigger_id
}

output "built_image_url" {
  description = "Built Docker image URL"
  value       = "${local.built_image}:latest"
}
