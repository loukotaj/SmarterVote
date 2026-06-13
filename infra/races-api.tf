# Cloud Run Service for races API
resource "google_cloud_run_v2_service" "races_api" {
  name     = "races-api-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/smartervote-${var.environment}/races-api:${var.app_version}"

      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.sv_data.name
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "DATA_DIR"
        value = "/app/data/published/"
      }

      env {
        name  = "CACHE_TTL_SECONDS"
        value = "3600"
      }

      env {
        name  = "ANALYTICS_PUBLIC_ONLY"
        value = "true"
      }

      env {
        name  = "ANALYTICS_LOG_4XX"
        value = "false"
      }

      env {
        name  = "ANALYTICS_SAMPLE_RATE"
        value = "1.0"
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "CLOUDFLARE_ANALYTICS_ACCOUNT_TAG"
        value = var.cloudflare_analytics_account_tag
      }

      env {
        name  = "CLOUDFLARE_ANALYTICS_SITE_TAG"
        value = var.cloudflare_analytics_site_tag
      }

      env {
        name = "CLOUDFLARE_ANALYTICS_API_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cloudflare_analytics_api_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "FIRESTORE_PROJECT"
        value = var.project_id
      }

      env {
        name = "OPENROUTER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openrouter_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ADMIN_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.admin_api_key.secret_id
            version = "latest"
          }
        }
      }

      # Auth0 JWT for admin endpoint protection (replaces pipeline-client auth)
      env {
        name  = "AUTH0_DOMAIN"
        value = var.auth0_domain
      }

      env {
        name  = "AUTH0_AUDIENCE"
        value = var.auth0_audience
      }

      # GCS bucket name (also exposed as GCS_BUCKET for admin GCS helpers)
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.sv_data.name
      }

      resources {
        limits = {
          cpu    = "1000m"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 12
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
        period_seconds = 30
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    service_account = google_service_account.races_api.email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    prevent_destroy = true

    ignore_changes = [
      template[0].annotations,
    ]

    create_before_destroy = true
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.openrouter_key,
    google_secret_manager_secret_version.admin_api_key,
    google_secret_manager_secret_version.cloudflare_analytics_api_token,
    google_secret_manager_secret_iam_member.races_api_openrouter_key,
    google_secret_manager_secret_iam_member.races_api_cloudflare_analytics,
  ]
}

# IAM for public access to races API
resource "google_cloud_run_v2_service_iam_binding" "races_api_invoker" {
  location = google_cloud_run_v2_service.races_api.location
  name     = google_cloud_run_v2_service.races_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}
