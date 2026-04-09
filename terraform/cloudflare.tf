# Cloudflare DNS Management
# API domain CNAME — points to Cloud Run's managed domain

data "cloudflare_zone" "zone" {
  count    = var.cloudflare_api_token != "" && var.cloudflare_api_token != "your-cloudflare-api-token" ? 1 : 0
  name     = var.cloudflare_zone_name
  provider = cloudflare
}

resource "cloudflare_record" "api_cname" {
  count           = var.cloudflare_api_token != "" && var.cloudflare_api_token != "your-cloudflare-api-token" ? 1 : 0
  zone_id         = data.cloudflare_zone.zone[0].id
  name            = var.api_domain
  type            = "CNAME"
  content         = "ghs.googlehosted.com"
  ttl             = var.dns_ttl
  proxied         = false  # Must be DNS-only for Cloud Run domain mapping (both Cloudflare and Cloud Run terminate SSL)
  allow_overwrite = true
  provider        = cloudflare
}
