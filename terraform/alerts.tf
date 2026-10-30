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
