# Cloud Run Service for pipeline client (V2 agent)
# DISABLED by default - set enable_pipeline_client = true in variables to deploy
# Run pipeline locally until ready to scale to cloud
resource "google_cloud_run_v2_service" "pipeline_client" {
  count    = var.enable_pipeline_client ? 1 : 0
  name     = "pipeline-client-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/smartervote-${var.environment}/pipeline-client:latest"

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "BUCKET_NAME"
        value = google_storage_bucket.sv_data.name
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.sv_data.name
      }

      env {
        name  = "FIRESTORE_PROJECT"
        value = var.project_id
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

      # Pipeline client configuration
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "LOG_LEVEL"
        value = var.environment == "prod" ? "INFO" : "DEBUG"
      }

      env {
        name  = "ALLOWED_ORIGINS"
        value = join(",", var.allowed_origins)
      }

      env {
        name  = "AUTH0_DOMAIN"
        value = var.auth0_domain
      }

      env {
        name  = "AUTH0_AUDIENCE"
        value = var.auth0_audience
      }

      env {
        name  = "STORAGE_MODE"
        value = "gcp"
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      ports {
        container_port = 8001
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    service_account = google_service_account.pipeline_client[0].email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
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

# Public access to pipeline client at Cloud Run level
# Authentication is enforced at the application level using Auth0 JWT tokens
# All sensitive endpoints require valid Auth0 authentication via verify_token dependency
resource "google_cloud_run_v2_service_iam_binding" "pipeline_client_invoker" {
  count    = var.enable_pipeline_client ? 1 : 0
  location = google_cloud_run_v2_service.pipeline_client[0].location
  name     = google_cloud_run_v2_service.pipeline_client[0].name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}
