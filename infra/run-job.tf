# Cloud Run Job for race processing pipeline (V2 agent)
# DISABLED by default - set enable_pipeline_client = true in variables to deploy
resource "google_cloud_run_v2_job" "race_worker" {
  count    = var.enable_pipeline_client ? 1 : 0
  name     = "race-worker-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    template {
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/smartervote-${var.environment}/pipeline:latest"

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
          name = "SERPER_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.serper_key.secret_id
              version = "latest"
            }
          }
        }

        # System Configuration
        env {
          name  = "ENVIRONMENT"
          value = var.environment
        }

        env {
          name  = "LOG_LEVEL"
          value = var.environment == "prod" ? "INFO" : "DEBUG"
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }

      timeout     = "3600s" # 1 hour timeout
      max_retries = 3

      service_account = google_service_account.race_worker[0].email
    }
  }

  lifecycle {
    prevent_destroy = false

    ignore_changes = [
      template[0].annotations,
    ]

    create_before_destroy = true
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.openai_key,
    google_secret_manager_secret_version.serper_key,
  ]
}
