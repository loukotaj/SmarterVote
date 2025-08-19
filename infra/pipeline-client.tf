# Cloud Run Service for pipeline client
resource "google_cloud_run_v2_service" "pipeline_client" {
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

      env {
        name = "GOOGLE_SEARCH_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.google_search_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GOOGLE_SEARCH_CX"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.google_search_cx.secret_id
            version = "latest"
          }
        }
      }

      # ChromaDB configuration
      env {
        name  = "CHROMA_CHUNK_SIZE"
        value = tostring(var.chroma_chunk_size)
      }

      env {
        name  = "CHROMA_CHUNK_OVERLAP"
        value = tostring(var.chroma_chunk_overlap)
      }

      env {
        name  = "CHROMA_EMBEDDING_MODEL"
        value = var.chroma_embedding_model
      }

      env {
        name  = "CHROMA_SIMILARITY_THRESHOLD"
        value = tostring(var.chroma_similarity_threshold)
      }

      env {
        name  = "CHROMA_MAX_RESULTS"
        value = tostring(var.chroma_max_results)
      }

      env {
        name  = "CHROMA_PERSIST_DIR"
        value = var.chroma_persist_dir
      }

      env {
        name  = "CHROMA_BUCKET_NAME"
        value = google_storage_bucket.chroma_storage.name
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
          memory = "4Gi"
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

    service_account = google_service_account.pipeline_client.email
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
    google_secret_manager_secret_version.anthropic_key,
    google_secret_manager_secret_version.grok_key,
    google_secret_manager_secret_version.google_search_key,
    google_secret_manager_secret_version.google_search_cx,
    google_storage_bucket.chroma_storage
  ]
}

# Public access to pipeline client
resource "google_cloud_run_v2_service_iam_binding" "pipeline_client_invoker" {
  location = google_cloud_run_v2_service.pipeline_client.location
  name     = google_cloud_run_v2_service.pipeline_client.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}
