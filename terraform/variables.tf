# Render API Configuration
variable "render_api_key" {
  description = "Render API key for authentication"
  type        = string
  sensitive   = true
}

variable "render_owner_id" {
  description = "Render account owner ID or team ID"
  type        = string
  sensitive   = true
}

# Service Configuration
variable "service_name" {
  description = "Name of the Render web service"
  type        = string
  default     = "beats-api"
}

variable "service_plan" {
  description = "Render service plan (free, starter, standard, pro, etc.)"
  type        = string
  default     = "free"
}

variable "region" {
  description = "Render region to deploy to"
  type        = string
  default     = "oregon"
}

# GitHub Repository Configuration
variable "github_repo_url" {
  description = "GitHub repository URL (format: https://github.com/owner/repo)"
  type        = string
  default     = "https://github.com/lanterno/beats"
}

variable "github_branch" {
  description = "Git branch to deploy from"
  type        = string
  default     = "main"
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

variable "auto_deploy" {
  description = "Enable auto-deploy on git push"
  type        = bool
  default     = true
}

# Custom Domain Configuration (optional)
variable "custom_domain" {
  description = "Custom domain to attach to the web service (e.g., beats.elghareeb.space). Leave empty to disable."
  type        = string
  default     = ""
}
