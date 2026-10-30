# Alerts on what monitoring.tf watches, sent by email to var.alert_email.
# Each threshold was set against the last 7 to 30 days of traffic (to
# 2026-10-30), so that none of them fires on an ordinary day; the comment on
# each says what it would have done in that time.

resource "google_monitoring_notification_channel" "email" {
  display_name = "${local.web_host} alerts"
  project      = var.project_id
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.monitoring]
}

locals {
  alert_channels = [google_monitoring_notification_channel.email.id]
}

# An alert compares with > or <, never >= (only COMPARISON_GT and
# COMPARISON_LT are supported), so "at least n" is written "more than n - 1".
#
# A condition on something that can fall silent (a 5xx count, a log-based
# metric) reads missing data as false, so its incident closes when the trouble
# stops rather than staying open until auto-close.

# Either host fails from more than one of the six probe locations. One
# location failing alone is usually the probe's network, not the site.
resource "google_monitoring_alert_policy" "uptime" {
  display_name          = "Uptime check failing"
  project               = var.project_id
  combiner              = "OR"
  severity              = "CRITICAL"
  notification_channels = local.alert_channels

  conditions {
    display_name = "More than one probe location fails"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type=\"uptime_url\"",
        "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\"",
        "metric.label.check_id=one_of(\"${google_monitoring_uptime_check_config.api_health.uptime_check_id}\", \"${google_monitoring_uptime_check_config.web.uptime_check_id}\")",
      ])

      # Each location's latest result in the last 20 minutes (the checks run
      # every five), then the number of locations whose latest result failed.
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "60s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      An uptime check on ${var.api_domain}/health or ${local.web_host}/ is failing from more than one probe location. The failed checks are in Logging with their reason (DNS, TLS, timeout, status or content). /health does not touch MongoDB: if it passes while the app fails, look at the database.
    EOT
  }
}

# More than 2% of the API's requests over five minutes answered 5xx, and at
# least three of them. At night five minutes can hold under 40 requests, when
# one error alone is over 2%; the count keeps a single error from paging. In
# the week to 2026-10-30 this would have fired twice: twelve companion
# requests failing within a minute on 10-27, and four on 10-26.
resource "google_monitoring_alert_policy" "api_5xx" {
  display_name          = "${var.api_service_name}: more than 2% of requests answered 5xx"
  project               = var.project_id
  combiner              = "AND"
  severity              = "ERROR"
  notification_channels = local.alert_channels

  conditions {
    display_name = "5xx share of requests over 5 minutes above 2%"

    condition_threshold {
      filter             = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_count\" AND metric.label.response_code_class=\"5xx\""
      denominator_filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_count\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      denominator_aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      comparison              = "COMPARISON_GT"
      threshold_value         = 0.02
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
    }
  }

  conditions {
    display_name = "At least three 5xx in those 5 minutes"

    condition_threshold {
      filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_count\" AND metric.label.response_code_class=\"5xx\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      comparison              = "COMPARISON_GT"
      threshold_value         = 2
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      ${var.api_service_name} is failing requests. The request log has each one (httpRequest.status>=500), and the API's own log lines beside it carry the traceback.
    EOT
  }
}

# p95 latency over ten minutes above 5 s. The target is 2 s, but today the
# API is over 2 s in about 13% of ten-minute windows, every day: most slow
# requests are the companion's polls of /api/projects/{id}/ledger. At 2 s this
# would page daily for a cause already known; at 5 s it would have fired in 3
# windows in the week to 2026-10-30. Bring it down once the ledger is fast.
resource "google_monitoring_alert_policy" "api_latency" {
  display_name          = "${var.api_service_name}: p95 latency above 5 s"
  project               = var.project_id
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.alert_channels

  conditions {
    display_name = "p95 over 10 minutes above 5 s"

    condition_threshold {
      filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/request_latencies\""

      # Each series' requests over the window, merged, then the 95th
      # percentile of them all.
      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_95"
        group_by_fields      = ["resource.label.service_name"]
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 5000
      duration        = "0s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      ${var.api_service_name} has been slow for ten minutes. The dashboard shows whether instances are at their maximum or starting cold (a cold start takes about 30 s); the request log, filtered on httpRequest.latency>"5s", shows which routes.
    EOT
  }
}

# A revision's active instances at max_instances (the variable behind
# maxScale in cloudrun.tf) for ten minutes: new requests wait for a free
# instance, and Cloud Run turns away (429) those that wait too long. At the
# current maximum of 2 this held for five minutes three times in the week to
# 2026-10-30, and for ten minutes twice.
resource "google_monitoring_alert_policy" "api_instances_at_max" {
  display_name          = "${var.api_service_name}: instances at the maximum"
  project               = var.project_id
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.alert_channels

  conditions {
    display_name = "Active instances at max_instances for 10 minutes"

    condition_threshold {
      filter = "${local.api_metrics} AND metric.type=\"run.googleapis.com/container/instance_count\" AND metric.label.state=\"active\""

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.revision_name"]
      }

      comparison      = "COMPARISON_GT"
      threshold_value = var.max_instances - 1
      duration        = "600s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      Every instance ${var.api_service_name} may run has been busy for ten minutes. Slow requests hold instances (see the latency chart); if traffic has simply grown, raise max_instances in the tfvars.
    EOT
  }
}

# Abuse signals, on monitoring.tf's log-based metrics. A policy on a
# log-based metric can only be created once the metric is visible to Cloud
# Monitoring, up to ten minutes after the metric itself; the two land in
# separate deploys so the apply never races it.

# More than 20 failures (401, 403, 404, 429) on one public route in ten
# minutes: someone trying passkey or SSO sign-ins, report links or pairing
# codes. In the 30 days to 2026-10-30 the most on any route was 7 (404s on
# /api/auth/sso); sign-in, report links and pairing had none at all. The
# routes' rate limits let through 5 to 30 attempts a minute, so even a slow
# guesser crosses 20 within minutes, while a person mistyping a code or
# reloading a revoked link (the report page does not retry) stays well under
# it.
resource "google_monitoring_alert_policy" "public_route_failures" {
  display_name          = "${var.api_service_name}: failures spiking on a public route"
  project               = var.project_id
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.alert_channels

  conditions {
    display_name = "More than 20 failures on one public route in 10 minutes"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type=\"cloud_run_revision\"",
        "metric.type=\"logging.googleapis.com/user/${google_logging_metric.public_route_requests.name}\"",
        "metric.label.status=one_of(\"401\", \"403\", \"404\", \"429\")",
      ])

      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["metric.label.route"]
      }

      comparison              = "COMPARISON_GT"
      threshold_value         = 20
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      A public route of ${var.api_service_name} is failing more than 20 times in ten minutes; the incident names the route. Query the request log for that route and group by httpRequest.remoteIp to see who is behind it.
    EOT
  }
}

# More than 200 rejections (401, 403, 429) under /api/ in ten minutes. In the
# 30 days to 2026-10-30 the most was 52, scanners probing paths like
# /api/.env; next came 48 403s from a companion build that called a route its
# device token may not, since fixed. 200 is four times either, low enough to
# catch a client stuck retrying with a revoked token or someone spraying
# tokens.
resource "google_monitoring_alert_policy" "api_rejections" {
  display_name          = "${var.api_service_name}: rejections spiking"
  project               = var.project_id
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.alert_channels

  conditions {
    display_name = "More than 200 rejections under /api/ in 10 minutes"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type=\"cloud_run_revision\"",
        "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_rejections.name}\"",
      ])

      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      comparison              = "COMPARISON_GT"
      threshold_value         = 200
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      ${var.api_service_name} has turned away more than 200 requests under /api/ in ten minutes. The dashboard splits them by status; the request log, grouped by httpRequest.remoteIp and httpRequest.userAgent, shows whether it is one client retrying or many addresses.
    EOT
  }
}
