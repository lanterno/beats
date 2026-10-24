# Cloudflare DNS Management
# API domain CNAME — points to Cloud Run's managed domain

data "cloudflare_zone" "zone" {
  count = var.cloudflare_api_token != "" && var.cloudflare_api_token != "your-cloudflare-api-token" ? 1 : 0
  filter = {
    name = var.cloudflare_zone_name
  }
}

# Provider 5 renamed cloudflare_record to cloudflare_dns_record and dropped
# allow_overwrite; an existing record is adopted with `terraform import`
# (README, "Cloudflare DNS Management"), not re-created.
resource "cloudflare_dns_record" "api_cname" {
  count   = var.cloudflare_api_token != "" && var.cloudflare_api_token != "your-cloudflare-api-token" ? 1 : 0
  zone_id = data.cloudflare_zone.zone[0].id
  name    = var.api_domain
  type    = "CNAME"
  content = "ghs.googlehosted.com"
  ttl     = var.dns_ttl
  proxied = false # Must be DNS-only for Cloud Run domain mapping (both Cloudflare and Cloud Run terminate SSL)
}
