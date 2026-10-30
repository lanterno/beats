# Production monitoring for lifepete.com: is it up, is the API fast and
# error-free, and who is being turned away. Nothing here pages anyone; it is
# for reading, in the Cloud Monitoring console.

locals {
  # The web app's host. Passkeys are bound to the web app's origin, so
  # var.webauthn_origin is where this configuration already names it.
  web_host = regex("^https://([^/:]+)", var.webauthn_origin)[0]

  # Cloud Run's own request log for the API: one entry per request, written
  # by Cloud Run, with httpRequest.status, .requestUrl, .latency and .remoteIp
  # (the caller's real address, which the API behind Cloud Run's proxy does
  # not see). The log-based metrics below read it, so the API logs nothing
  # extra for them.
  api_request_log = chomp(<<-EOT
    resource.type="cloud_run_revision"
    AND resource.labels.service_name="${var.api_service_name}"
    AND log_id("run.googleapis.com/requests")
  EOT
  )
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

# Log-based metrics count from the moment they exist; they are not backfilled.

# Rejections: 401, 403 and 429 on the API's own paths, /api/. Almost every
# other 401 is a scanner probing for files (/.env, /phpinfo.php,
# /credentials.json), which the API answers 401 because they need a session:
# 6,607 of the 6,949 401s in the 30 days to 2026-10-30. Counted here, they
# would drown the rejections that mean something.
resource "google_logging_metric" "api_rejections" {
  name        = "${var.api_service_name}/rejections"
  project     = var.project_id
  description = "Requests under /api/ answered 401, 403 or 429, by status."
  filter = chomp(<<-EOT
    ${local.api_request_log}
    AND httpRequest.requestUrl=~"^https?://[^/]+/api/"
    AND (httpRequest.status=401 OR httpRequest.status=403 OR httpRequest.status=429)
  EOT
  )

  label_extractors = {
    status = "EXTRACT(httpRequest.status)"
  }

  metric_descriptor {
    display_name = "${var.api_service_name} rejections"
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"

    labels {
      key         = "status"
      value_type  = "STRING"
      description = "401, 403 or 429."
    }
  }

  depends_on = [google_project_service.logging]
}

# Every request to the routes that need no session (PUBLIC_PREFIXES in
# api/src/server.py): passkey sign-in and registration, single sign-on, a
# client's report link and a device's pairing code. /health is public too,
# but there is nothing to guess there. By route and status, because each
# route fails in its own way: a passkey or SSO sign-in that fails is a 401,
# while a report link or pairing code that does not exist is a 404, so
# guessing either would never show among the 401s. Past the per-address
# limit, any of them answers 429.
resource "google_logging_metric" "public_route_requests" {
  name        = "${var.api_service_name}/public_route_requests"
  project     = var.project_id
  description = "Requests to the API's public routes, by route and status."
  filter = chomp(<<-EOT
    ${local.api_request_log}
    AND httpRequest.requestUrl=~"^https?://[^/]+/api/(auth|reports|device/pair/exchange)(/|[?]|$)"
  EOT
  )

  label_extractors = {
    # auth/sso before auth: the first alternative that matches wins.
    route  = "REGEXP_EXTRACT(httpRequest.requestUrl, \"^https?://[^/]+/api/(auth/sso|auth|reports|device/pair/exchange)\")"
    status = "EXTRACT(httpRequest.status)"
  }

  metric_descriptor {
    display_name = "${var.api_service_name} public-route requests"
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"

    labels {
      key         = "route"
      value_type  = "STRING"
      description = "The route under /api/: auth, auth/sso, reports or device/pair/exchange."
    }

    labels {
      key         = "status"
      value_type  = "STRING"
      description = "The HTTP status of the response."
    }
  }

  depends_on = [google_project_service.logging]
}
