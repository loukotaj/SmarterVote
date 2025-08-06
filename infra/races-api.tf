# Cloud Run Service for races API
resource "google_cloud_run_v2_service" "races_api" {
  name     = "races-api-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/smartervote-${var.environment}/races-api:latest"

      env {
        name  = "BUCKET_NAME"
        value = google_storage_bucket.sv_data.name
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "DATA_DIR"
        value = "/app/data"
      }

      env {
        name  = "PUBLISHED_DATA_PATH"
        value = "out/"
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

    service_account = google_service_account.races_api.email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

# IAM for public access to races API
resource "google_cloud_run_v2_service_iam_binding" "races_api_invoker" {
  location = google_cloud_run_v2_service.races_api.location
  name     = google_cloud_run_v2_service.races_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}
