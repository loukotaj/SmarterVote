# Pub/Sub topic for race processing jobs
resource "google_pubsub_topic" "race_jobs" {
  name = "race-jobs"
  
  message_retention_duration = "86400s"  # 24 hours
}

# Pub/Sub subscription for race processing
resource "google_pubsub_subscription" "race_jobs_sub" {
  name  = "race-jobs-sub"
  topic = google_pubsub_topic.race_jobs.name
  
  ack_deadline_seconds = 600  # 10 minutes
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.race_jobs_dlq.id
    max_delivery_attempts = 5
  }
  
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.enqueue_api.uri}/webhook"
    
    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
    }
  }
}

# Dead letter queue for failed jobs
resource "google_pubsub_topic" "race_jobs_dlq" {
  name = "race-jobs-dlq"
  
  message_retention_duration = "604800s"  # 7 days
}

resource "google_pubsub_subscription" "race_jobs_dlq_sub" {
  name  = "race-jobs-dlq-sub"
  topic = google_pubsub_topic.race_jobs_dlq.name
  
  # Manual acknowledgment for investigation
  ack_deadline_seconds = 600
}
