# Google Cloud Configuration
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region to deploy to (e.g., us-central1, europe-west1)"
  type        = string
  default     = "us-central1"
}

# Service Configuration
variable "api_service_name" {
  description = "Name of the Cloud Run service"
  type        = string
  default     = "beats-api"
}

variable "container_port" {
  description = "Port the container listens on (Cloud Run sets PORT env var automatically)"
  type        = number
  default     = 8080
}

variable "cpu_limit" {
  description = "CPU limit per container instance"
  type        = string
  default     = "1000m"
}

variable "memory_limit" {
  description = "Memory limit per container instance"
  type        = string
  default     = "256Mi"
}

variable "container_concurrency" {
  description = "Maximum number of concurrent requests per container instance"
  type        = number
  default     = 80
}

variable "request_timeout_seconds" {
  description = "Request timeout in seconds"
  type        = number
  default     = 300
}

variable "min_instances" {
  description = "Minimum number of container instances to keep running"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of container instances"
  type        = number
  default     = 2
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated access to the service"
  type        = bool
  default     = true
}

# Database Configuration
variable "mongodb_connection_string" {
  description = "MongoDB connection string (e.g., mongodb+srv://user:pass@cluster.mongodb.net)"
  type        = string
  sensitive   = true
}

variable "mongodb_database_name" {
  description = "MongoDB database name"
  type        = string
  default     = "beats"
}

# Application Configuration
variable "api_access_token" {
  description = "API access token for authentication"
  type        = string
  sensitive   = true
}

# WebAuthn Configuration
variable "webauthn_rp_id" {
  description = "WebAuthn Relying Party ID (domain name, e.g., lifepete.com)"
  type        = string
  default     = "lifepete.com"
}

variable "webauthn_origin" {
  description = "WebAuthn expected origin (full URL, e.g., https://lifepete.com)"
  type        = string
  default     = "https://lifepete.com"
}

# Custom Domain Configuration
variable "api_domain" {
  description = "Custom domain to attach to the Cloud Run service (e.g., api.beats.elghareeb.space)"
  type        = string
}

# Cloud Build Configuration
variable "github_owner" {
  description = "GitHub repository owner (username or organization)"
  type        = string
  default     = "lanterno"
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "beats"
}

variable "github_branch" {
  description = "GitHub branch to trigger builds on"
  type        = string
  default     = "main"
}

# Cloudflare Configuration
variable "cloudflare_api_token" {
  description = "Cloudflare API token for managing DNS records (required)"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_name" {
  description = "Cloudflare zone name (e.g., elghareeb.space)"
  type        = string
  default     = "elghareeb.space"
}

variable "dns_ttl" {
  description = "TTL for Cloudflare DNS records (in seconds). Use 1 for automatic."
  type        = number
  default     = 1
}

