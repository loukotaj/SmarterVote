# ---------------------------------------------------------------------------
# Firestore Database
# ---------------------------------------------------------------------------

resource "google_project_service" "firestore" {
  project                    = var.project_id
  service                    = "firestore.googleapis.com"
  disable_dependent_services = false

  depends_on = [google_project_service.apis]
}

resource "google_firestore_database" "analytics" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.firestore]

  lifecycle {
    prevent_destroy = false
  }
}

# ---------------------------------------------------------------------------
# IAM — Firestore access for both services
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "races_api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.races_api.email}"

  depends_on = [google_firestore_database.analytics]
}

resource "google_project_iam_member" "pipeline_client_firestore" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.pipeline_client[0].email}"

  depends_on = [google_firestore_database.analytics]
}

# ---------------------------------------------------------------------------
# Cloud Monitoring — notification channel (email) + alert policies
# Only created when alert_email is provided
# ---------------------------------------------------------------------------

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "SmarterVote Admin Email (${var.environment})"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
}

# Alert: races-api 5xx error rate > 5% sustained for 5 minutes
resource "google_monitoring_alert_policy" "races_api_errors" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "races-api High Error Rate (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "5xx responses > 5% for 5 minutes"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"races-api-${var.environment}\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "604800s"
  }

  depends_on = [google_monitoring_notification_channel.email]
}

# Alert: races-api receives zero traffic for 10 minutes (possible service down)
resource "google_monitoring_alert_policy" "races_api_no_traffic" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "races-api No Traffic (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Request count = 0 for 10 minutes"

    condition_absent {
      filter   = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"races-api-${var.environment}\" AND metric.type = \"run.googleapis.com/request_count\""
      duration = "600s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_COUNT"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "604800s"
  }

  depends_on = [google_monitoring_notification_channel.email]
}

# Log-based metric — pipeline ERROR log entries
resource "google_logging_metric" "pipeline_errors" {
  project     = var.project_id
  name        = "pipeline_errors_${var.environment}"
  description = "Count of ERROR-level log entries from the pipeline-client service"
  filter      = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"pipeline-client-${var.environment}\" AND severity = ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# Alert: pipeline error spike > 5 errors in 5 minutes
resource "google_monitoring_alert_policy" "pipeline_error_spike" {
  count        = var.alert_email != "" && var.enable_pipeline_client ? 1 : 0
  project      = var.project_id
  display_name = "pipeline-client Error Spike (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Pipeline ERROR logs > 5 in 5 minutes"

    condition_threshold {
      filter          = "metric.type = \"logging.googleapis.com/user/${google_logging_metric.pipeline_errors.name}\" AND resource.type = \"cloud_run_revision\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "604800s"
  }

  depends_on = [google_monitoring_notification_channel.email, google_logging_metric.pipeline_errors]
}
