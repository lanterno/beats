output "service_id" {
  description = "Render service ID"
  value       = render_web_service.beats_api.id
}

output "service_url" {
  description = "Public URL of the deployed service"
  value       = render_web_service.beats_api.url
}

output "service_name" {
  description = "Name of the deployed service"
  value       = render_web_service.beats_api.name
}

output "deploy_url" {
  description = "Dashboard URL to view the service"
  value       = "https://dashboard.render.com/web/${render_web_service.beats_api.id}"
}

output "service_host_for_dns" {
  description = "Host to use as CNAME target for your custom domain (copy the host from this URL)"
  value       = render_web_service.beats_api.url
}
