provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloudflare provider for DNS management
# Note: Provider will also check CLOUDFLARE_API_TOKEN environment variable as fallback
# Uses a dummy token if placeholder is provided (provider requires valid format, but resources won't be created)
provider "cloudflare" {
  api_token = var.cloudflare_api_token != "" && var.cloudflare_api_token != "your-cloudflare-api-token" ? var.cloudflare_api_token : "0000000000000000000000000000000000000000"
}

