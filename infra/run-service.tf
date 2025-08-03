# Cloud Run Service for enqueue API
resource "google_cloud_run_v2_service" "enqueue_api" {
  name     = "enqueue-api"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/smartervote-enqueue-api:latest"
      
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.race_jobs.name
      }
      
      env {
        name  = "CLOUD_RUN_JOB"
        value = google_cloud_run_v2_job.race_worker.name
      }
      
      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }
      
      ports {
        container_port = 8080
      }
    }
    
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    
    service_account = google_service_account.enqueue_api.email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

# IAM for public access to enqueue API
resource "google_cloud_run_v2_service_iam_binding" "enqueue_api_invoker" {
  location = google_cloud_run_v2_service.enqueue_api.location
  name     = google_cloud_run_v2_service.enqueue_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}
