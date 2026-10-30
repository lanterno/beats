# Production monitoring for lifepete.com: is it up, is the API fast and
# error-free, and who is being turned away. Nothing here pages anyone; it is
# for reading, in the Cloud Monitoring console.

locals {
  # The web app's host. Passkeys are bound to the web app's origin, so
  # var.webauthn_origin is where this configuration already names it.
  web_host = regex("^https://([^/:]+)", var.webauthn_origin)[0]
}

# Uptime checks run from every region Google probes from (six locations), once
# every five minutes each: 72 requests an hour per check. At one-minute checks
# the probes would be nearly a third of the API's traffic, and since /health
# answers in milliseconds they would pull down the latency the dashboard
# reports.

# The API. /health answers {"status": "healthy", ...} without touching
# MongoDB, so this says the service is up and reachable, not that the
# database is.
resource "google_monitoring_uptime_check_config" "api_health" {
  display_name = "${var.api_domain} /health"
  project      = var.project_id
  period       = "300s"
  timeout      = "10s"
  checker_type = "STATIC_IP_CHECKERS"

  # A failed check is logged with its reason (DNS, TLS, timeout, status).
  log_check_failures = true

  http_check {
    path           = "/health"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"

    accepted_response_status_codes {
      status_value = 200
    }
  }

  content_matchers {
    content = "healthy"
    matcher = "MATCHES_JSON_PATH"

    json_path_matcher {
      json_path    = "$.status"
      json_matcher = "EXACT_MATCH"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.api_domain
    }
  }

  depends_on = [google_project_service.monitoring]
}

# The web app, through Cloudflare to Firebase Hosting. The page must hold the
# element React mounts into (ui/index.html): a 200 without it is not the app.
resource "google_monitoring_uptime_check_config" "web" {
  display_name = "${local.web_host} /"
  project      = var.project_id
  period       = "300s"
  timeout      = "10s"
  checker_type = "STATIC_IP_CHECKERS"

  log_check_failures = true

  http_check {
    path           = "/"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"

    accepted_response_status_codes {
      status_value = 200
    }
  }

  content_matchers {
    content = "<div id=\"root\"></div>"
    matcher = "CONTAINS_STRING"
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = local.web_host
    }
  }

  depends_on = [google_project_service.monitoring]
}
