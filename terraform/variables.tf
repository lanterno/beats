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
variable "service_name" {
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
  default     = "1000m"  # 1 vCPU
}

variable "memory_limit" {
  description = "Memory limit per container instance"
  type        = string
  default     = "512Mi"
}

variable "container_concurrency" {
  description = "Maximum number of concurrent requests per container instance"
  type        = number
  default     = 80
}

variable "timeout_seconds" {
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
  default     = 10
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated access to the service"
  type        = bool
  default     = true
}

# Database Configuration
variable "db_dsn" {
  description = "MongoDB connection string (e.g., mongodb+srv://user:pass@cluster.mongodb.net)"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "MongoDB database name"
  type        = string
  default     = "beats"
}

# Application Configuration
variable "access_token" {
  description = "API access token for authentication"
  type        = string
  sensitive   = true
}

# Custom Domain Configuration
variable "custom_domain" {
  description = "Custom domain to attach to the Cloud Run service (e.g., beats.elghareeb.space)"
  type        = string
}

# Cloud SQL Configuration (optional)
variable "cloud_sql_instance" {
  description = "Cloud SQL instance connection name (format: PROJECT:REGION:INSTANCE). Leave empty if not using Cloud SQL."
  type        = string
  default     = ""
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

