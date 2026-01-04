# Pub/Sub topic for race processing jobs
# DISABLED by default - set enable_pipeline_client = true in variables to deploy
resource "google_pubsub_topic" "race_jobs" {
  count   = var.enable_pipeline_client ? 1 : 0
  name    = "race-jobs-${var.environment}"
  project = var.project_id

  message_retention_duration = "86400s" # 24 hours

  depends_on = [google_project_service.apis]
}

# Dead letter queue for failed jobs
resource "google_pubsub_topic" "race_jobs_dlq" {
  count   = var.enable_pipeline_client ? 1 : 0
  name    = "race-jobs-dlq-${var.environment}"
  project = var.project_id

  message_retention_duration = "604800s" # 7 days

  depends_on = [google_project_service.apis]
}

# Pub/Sub subscription for race processing
resource "google_pubsub_subscription" "race_jobs_sub" {
  count   = var.enable_pipeline_client ? 1 : 0
  name    = "race-jobs-sub-${var.environment}"
  topic   = google_pubsub_topic.race_jobs[0].name
  project = var.project_id

  ack_deadline_seconds = 600 # 10 minutes

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.race_jobs_dlq[0].id
    max_delivery_attempts = 5
  }

  # Note: Push endpoint will be configured after Cloud Run service is created
  # This is handled in run-service.tf to avoid circular dependencies

  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "race_jobs_dlq_sub" {
  count   = var.enable_pipeline_client ? 1 : 0
  name    = "race-jobs-dlq-sub-${var.environment}"
  topic   = google_pubsub_topic.race_jobs_dlq[0].name
  project = var.project_id

  # Manual acknowledgment for investigation
  ack_deadline_seconds = 600
}
