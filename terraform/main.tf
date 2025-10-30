terraform {
  required_version = ">= 1.10"
  
  required_providers {
    render = {
      source  = "render-oss/render"
      version = "~> 1.7.5"
    }
  }
}

provider "render" {
  api_key  = var.render_api_key
  owner_id = var.render_owner_id
}

# Web service for the Beats FastAPI application
resource "render_web_service" "beats_api" {
  name   = var.service_name
  plan   = var.service_plan
  region = var.region
  
  runtime_source = {
    docker = {
      dockerfile_path = "Dockerfile"
      docker_context  = "."
      repo_url        = var.github_repo_url
      branch          = var.github_branch
      auto_deploy     = var.auto_deploy
    }
  }
  
  # Environment variables
  env_vars = {
    PORT = {
      value = "10000"
    }
    DB_DSN = {
      value = var.db_dsn
    }
    DB_NAME = {
      value = var.db_name
    }
    ACCESS_TOKEN = {
      value = var.access_token
    }
  }
  
  # Health check configuration
  health_check_path = "/health"
}

# Note: The Render Terraform provider (v1.7.x) does not support managing custom domains.
# To use a custom domain (e.g., beats.elghareeb.space), add it in the Render dashboard
# under the Web Service -> Custom Domains, and create the suggested DNS record at your
# DNS provider. SSL will be provisioned automatically by Render.
