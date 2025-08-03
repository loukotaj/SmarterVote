# Cloud Run Job for race processing pipeline
resource "google_cloud_run_v2_job" "race_worker" {
  name     = "race-worker"
  location = var.region

  template {
    template {
      containers {
        image = "gcr.io/${var.project_id}/smartervote-pipeline:latest"
        
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        
        env {
          name  = "BUCKET_NAME"
          value = google_storage_bucket.sv_data.name
        }
        
        env {
          name = "OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.openai_key.secret_id
              version = "latest"
            }
          }
        }
        
        env {
          name = "ANTHROPIC_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.anthropic_key.secret_id
              version = "latest"
            }
          }
        }
        
        env {
          name = "GROK_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.grok_key.secret_id
              version = "latest"
            }
          }
        }
        
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }
      
      timeout = "3600s"  # 1 hour timeout
      max_retries = 3
      
      service_account = google_service_account.race_worker.email
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.openai_key,
    google_secret_manager_secret_version.anthropic_key,
    google_secret_manager_secret_version.grok_key
  ]
}
