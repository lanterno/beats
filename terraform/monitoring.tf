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
    content = jsonencode("healthy") # a JSON value, as the JSON-path matcher reads it
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

# One dashboard reading all of the above beside Cloud Run's own metrics:
# Monitoring > Dashboards in the Cloud console. Rates are per second whatever
# the time range, so a chart reads the same zoomed in or out.
#
# A tile in the first row or column leaves out yPos or xPos rather than
# saying 0: the API drops zero positions, and the provider would then see a
# change to the dashboard on every apply.
locals {
  api_metrics = "resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"${var.api_service_name}\""
}

resource "google_monitoring_dashboard" "api" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "${var.api_service_name} and ${local.web_host}"
    mosaicLayout = {
      columns = 48
      tiles = [
        {
          width  = 48
          height = 7
          widget = {
            title = "Reading this dashboard"
            text = {
              format  = "MARKDOWN"
              content = <<-EOT
                Machines make most of the API's requests: the companion, the daemon and the wall clock poll it, and the uptime check calls `/health` 72 times an hour. The rejections leave out paths outside `/api/`, which are nearly all scanners probing for files.

                To see who is behind a spike, open the request log in Logs Explorer (`log_id("run.googleapis.com/requests")` on `${var.api_service_name}`): `httpRequest.remoteIp` is the caller's address.
              EOT
            }
          }
        },
        {
          yPos   = 7
          width  = 24
          height = 16
          widget = {
            title = "Requests per second, by response class"
            xyChart = {
              dataSets = [{
                plotType       = "STACKED_AREA"
                legendTemplate = "$${metric.labels.response_code_class}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_count\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["metric.label.response_code_class"]
                    }
                  }
                }
              }]
              yAxis = { label = "requests/s", scale = "LINEAR" }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 7
          width  = 24
          height = 16
          widget = {
            title = "Share of requests answered 5xx"
            xyChart = {
              dataSets = [{
                plotType       = "LINE"
                legendTemplate = "5xx"
                timeSeriesQuery = {
                  timeSeriesFilterRatio = {
                    numerator = {
                      filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_count\" AND metric.label.response_code_class=\"5xx\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["resource.label.service_name"]
                      }
                    }
                    denominator = {
                      filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_count\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["resource.label.service_name"]
                      }
                    }
                  }
                }
              }]
              yAxis = { label = "share of requests", scale = "LINEAR" }
            }
          }
        },
        {
          yPos   = 23
          width  = 24
          height = 16
          widget = {
            title = "Request latency, percentiles"
            xyChart = {
              dataSets = [for p in [50, 95, 99] : {
                plotType       = "LINE"
                legendTemplate = "p${p}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_latencies\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_DELTA"
                      crossSeriesReducer = "REDUCE_PERCENTILE_${p}"
                      groupByFields      = ["resource.label.service_name"]
                    }
                  }
                }
              }]
              yAxis = { label = "ms", scale = "LINEAR" }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 23
          width  = 24
          height = 16
          widget = {
            title = "Instances, by state"
            xyChart = {
              dataSets = [{
                plotType       = "STACKED_AREA"
                legendTemplate = "$${metric.labels.state}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/container/instance_count\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_MAX"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["metric.label.state"]
                    }
                  }
                }
              }]
              # The same variable that sets the service's maxScale (cloudrun.tf).
              thresholds = [{ label = "max instances", value = var.max_instances }]
              yAxis      = { label = "instances", scale = "LINEAR" }
            }
          }
        },
        {
          yPos   = 39
          width  = 24
          height = 16
          widget = {
            title = "Container startup latency: each point is a cold start"
            xyChart = {
              dataSets = [for p in [50, 99] : {
                plotType       = "LINE"
                legendTemplate = "p${p}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/container/startup_latencies\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_DELTA"
                      crossSeriesReducer = "REDUCE_PERCENTILE_${p}"
                      groupByFields      = ["resource.label.service_name"]
                    }
                  }
                }
              }]
              yAxis = { label = "ms", scale = "LINEAR" }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 39
          width  = 24
          height = 16
          widget = {
            title = "Uptime checks: share of probe locations passing"
            xyChart = {
              dataSets = [{
                plotType       = "LINE"
                legendTemplate = "$${resource.labels.host}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = join(" AND ", [
                      "resource.type=\"uptime_url\"",
                      "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\"",
                      "metric.label.check_id=one_of(\"${google_monitoring_uptime_check_config.api_health.uptime_check_id}\", \"${google_monitoring_uptime_check_config.web.uptime_check_id}\")",
                    ])
                    aggregation = {
                      alignmentPeriod    = "300s"
                      perSeriesAligner   = "ALIGN_FRACTION_TRUE"
                      crossSeriesReducer = "REDUCE_MEAN"
                      groupByFields      = ["resource.label.host"]
                    }
                  }
                }
              }]
              yAxis = { label = "share passing", scale = "LINEAR" }
            }
          }
        },
        {
          yPos   = 55
          width  = 24
          height = 16
          widget = {
            title = "Rejections under /api/ per second, by status"
            xyChart = {
              dataSets = [{
                plotType       = "STACKED_BAR"
                legendTemplate = "$${metric.labels.status}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_rejections.name}\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["metric.label.status"]
                    }
                  }
                }
              }]
              yAxis = { label = "requests/s", scale = "LINEAR" }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 55
          width  = 24
          height = 16
          widget = {
            title = "Public routes per second, by route and status"
            xyChart = {
              dataSets = [{
                plotType       = "STACKED_BAR"
                legendTemplate = "$${metric.labels.route} $${metric.labels.status}"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.public_route_requests.name}\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["metric.label.route", "metric.label.status"]
                    }
                  }
                }
              }]
              yAxis = { label = "requests/s", scale = "LINEAR" }
            }
          }
        },
      ]
    }
  })

  depends_on = [google_project_service.monitoring]
}
