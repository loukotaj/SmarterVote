# Cloud Scheduler for nightly race processing
resource "google_cloud_scheduler_job" "nightly_processing" {
  name        = "nightly-race-processing"
  description = "Trigger nightly processing of all active races"
  schedule    = "0 2 * * *"  # 2 AM UTC daily
  time_zone   = "UTC"
  region      = var.region
  
  pubsub_target {
    topic_name = google_pubsub_topic.race_jobs.id
    data = base64encode(jsonencode({
      job_type = "batch_process"
      trigger  = "scheduler"
      races    = "all_active"
    }))
  }
  
  depends_on = [google_project_service.apis]
}

# Weekly full refresh (more comprehensive processing)
resource "google_cloud_scheduler_job" "weekly_refresh" {
  name        = "weekly-race-refresh"
  description = "Weekly full refresh of all race data"
  schedule    = "0 1 * * 0"  # 1 AM UTC every Sunday
  time_zone   = "UTC"
  region      = var.region
  
  pubsub_target {
    topic_name = google_pubsub_topic.race_jobs.id
    data = base64encode(jsonencode({
      job_type = "full_refresh"
      trigger  = "scheduler"
      races    = "all"
      force_fresh_search = true
    }))
  }
  
  depends_on = [google_project_service.apis]
}
