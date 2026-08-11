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
  count       = var.create_firestore_database ? 1 : 0
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.firestore]

  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# IAM — Firestore access for both services
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "races_api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.races_api.email}"
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

# Alert: races-api 5xx response rate sustained for 5 minutes
resource "google_monitoring_alert_policy" "races_api_errors" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "races-api High Error Rate (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "5xx responses > 0.05/sec for 5 minutes"

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

# Alert: races-api p95 latency > 2 seconds sustained for 5 minutes
resource "google_monitoring_alert_policy" "races_api_latency" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "races-api High Latency (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "p95 latency > 2s for 5 minutes"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"races-api-${var.environment}\" AND metric.type = \"run.googleapis.com/request_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2000

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
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

# ---------------------------------------------------------------------------
# Cloud Monitoring — pipeline Cloud Run Job (runner="cloud_run")
# Covers only the one-shot Cloud Run Job path. It does NOT cover
# runner="local" (the permanent Docker worker) — see the `local_worker_stale`
# alert further below for that runner instead.
# ---------------------------------------------------------------------------

# Alert: any failed task attempt on the pipeline Cloud Run Job in a 15-minute
# window. Each execution is a single task with max_retries = 0
# (infra/pipeline-job.tf), so one failure means one race run failed outright
# with no automatic retry — worth alerting on immediately rather than waiting
# for a sustained rate.
resource "google_monitoring_alert_policy" "pipeline_job_failures" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "pipeline-job Execution Failures (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Failed task attempts > 0 in 15 minutes"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_job\" AND resource.labels.job_name = \"pipeline-job-${var.environment}\" AND metric.type = \"run.googleapis.com/job/completed_task_attempt_count\" AND metric.labels.result = \"failed\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_COUNT"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.job_name"]
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "604800s"
  }

  depends_on = [google_monitoring_notification_channel.email]
}

# ---------------------------------------------------------------------------
# Cloud Monitoring — Firestore `pipeline_queue` backlog depth
#
# No native GCP metric exposes "how many pipeline_queue docs are pending", so
# this alert is backed by a log-based metric parsing a line races-api already
# logs on every `GET /api/queue` call (services/races-api/routers/queue.py,
# get_queue()):
#
#   logger.info("pipeline_queue_depth pending=%d running=%d", pending, running)
#
# VERIFIED: that line was added alongside this Terraform change specifically
# to back this metric (it did not previously exist — no other pipeline_queue
# backlog signal was found anywhere in pipeline_client/ or services/races-api/).
# That endpoint is otherwise only hit when the admin dashboard happens to be
# open, so the Cloud Scheduler job below polls it every 5 minutes purely to
# keep this signal flowing regardless of dashboard usage.
# ---------------------------------------------------------------------------

resource "google_logging_metric" "pipeline_queue_pending_depth" {
  count       = var.alert_email != "" ? 1 : 0
  name        = "pipeline_queue_pending_depth-${var.environment}"
  project     = var.project_id
  description = "Extracted 'pending' count from races-api's pipeline_queue_depth log line (services/races-api/routers/queue.py get_queue())."
  filter      = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"races-api-${var.environment}\" AND textPayload =~ \"pipeline_queue_depth pending=[0-9]+\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "1"
  }

  value_extractor = "REGEXP_EXTRACT(textPayload, \"pipeline_queue_depth pending=(\\\\d+)\")"

  bucket_options {
    linear_buckets {
      num_finite_buckets = 64
      width              = 5
      offset             = 0
    }
  }
}

# Cloud Scheduler -> races-api GET /api/queue, solely to keep the log line
# above flowing on a fixed cadence. Authenticates with X-Admin-Key the same
# way other non-browser admin clients do (services/races-api/auth.py
# verify_token already accepts this header), so it only gets created when
# admin_api_key is actually set.
resource "google_cloud_scheduler_job" "queue_backlog_check" {
  count       = nonsensitive(var.alert_email != "" && var.admin_api_key != "") ? 1 : 0
  project     = var.project_id
  region      = var.region
  name        = "queue-backlog-check-${var.environment}"
  description = "Periodically hits races-api /api/queue so the pipeline_queue_depth log line (and the backlog alert built on it) keeps flowing even when no admin has the dashboard open."
  schedule    = "*/5 * * * *"
  time_zone   = "Etc/UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.races_api.uri}/api/queue?active_only=true"
    http_method = "GET"

    headers = {
      "X-Admin-Key" = var.admin_api_key
    }
  }

  retry_config {
    retry_count = 1
  }

  depends_on = [google_project_service.apis, google_cloud_run_v2_service.races_api]
}

# Alert: pipeline_queue backlog (pending items) stays elevated for 30 minutes.
# The threshold of 15 is a starting estimate for "more queued than either
# runner can reasonably be draining promptly" — revisit once real backlog
# data exists.
resource "google_monitoring_alert_policy" "queue_backlog_elevated" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "pipeline_queue Backlog Elevated (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Pending queue depth > 15 sustained for 30 minutes"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.pipeline_queue_pending_depth[0].name}\""
      duration        = "1800s"
      comparison      = "COMPARISON_GT"
      threshold_value = 15

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MAX"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "604800s"
  }

  depends_on = [google_monitoring_notification_channel.email, google_logging_metric.pipeline_queue_pending_depth]
}

# ---------------------------------------------------------------------------
# Cloud Monitoring — stale local Docker worker (runner="local")
#
# The local worker (docker-compose.worker.yml) has no Terraform resource and
# does not auto-update or auto-restart as part of this project's deploy path
# (see CLAUDE.md's "Priority Model" section). This alert fires when it stops
# proving it's alive at all — it does NOT prove the worker is running current
# code, only that the process is up and polling. It is backed by a heartbeat
# log line the worker itself writes directly to Cloud Logging
# (pipeline_client/worker.py, `_emit_heartbeat()`/`_get_cloud_logger()`),
# fired on a fixed interval independent of whether any race is in flight:
#
#   cloud_logger.log_struct({"event": "pipeline_worker_heartbeat", ...})
#
# VERIFIED: no heartbeat/run-progress signal for the local worker previously
# existed anywhere in pipeline_client/ — the only prior "heartbeat" was
# queue_processor.py's per-item Firestore *lease* renewal
# (_start_lease_heartbeat), which only runs while a race is actively being
# processed and says nothing when the worker is simply idle between races.
# This is new, minimal instrumentation added alongside this alert.
#
# CAVEAT: this requires the workstation's ADC identity to hold
# roles/logging.logWriter (or broader) on the project. That IAM grant is
# intentionally NOT provisioned by this Terraform, because the local worker
# runs under the developer's own `gcloud auth application-default login`
# identity rather than a dedicated service account (see the setup comment in
# docker-compose.worker.yml) — Terraform has no service account of its own to
# grant that role to here. If the role is missing, `_get_cloud_logger()` logs
# a local warning once and the heartbeat silently stops shipping, which then
# looks identical to a genuinely dead worker.
# ---------------------------------------------------------------------------

resource "google_logging_metric" "pipeline_worker_heartbeat" {
  count       = var.alert_email != "" ? 1 : 0
  name        = "pipeline_worker_heartbeat-${var.environment}"
  project     = var.project_id
  description = "Counts pipeline_worker_heartbeat log entries emitted by the long-lived local Docker worker (pipeline_client/worker.py)."
  filter      = "logName = \"projects/${var.project_id}/logs/pipeline-worker-heartbeat\" AND jsonPayload.event = \"pipeline_worker_heartbeat\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# Alert: no local-worker heartbeat for 1 hour. Default heartbeat interval is
# 5 minutes (WORKER_HEARTBEAT_SECONDS in pipeline_client/worker.py), so an
# hour of silence means the container is stopped, crashed, or was never
# started/rebuilt after a fix — not just a slow poll cycle.
resource "google_monitoring_alert_policy" "local_worker_stale" {
  count        = var.alert_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "Local Pipeline Worker Stale (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "No pipeline_worker_heartbeat log entries for 1 hour"

    condition_absent {
      filter   = "metric.type = \"logging.googleapis.com/user/${google_logging_metric.pipeline_worker_heartbeat[0].name}\""
      duration = "3600s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_COUNT"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "604800s"
  }

  depends_on = [google_monitoring_notification_channel.email, google_logging_metric.pipeline_worker_heartbeat]
}
