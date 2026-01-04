# Cloud Run Service for enqueue API
# DISABLED by default - set enable_pipeline_client = true in variables to deploy
resource "google_cloud_run_v2_service" "enqueue_api" {
  count    = var.enable_pipeline_client ? 1 : 0
  name     = "enqueue-api-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/smartervote-${var.environment}/enqueue-api:latest"

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.race_jobs[0].name
      }

      env {
        name  = "CLOUD_RUN_JOB_NAME"
        value = google_cloud_run_v2_job.race_worker[0].name
      }

      env {
        name  = "REGION"
        value = var.region
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

    service_account = google_service_account.enqueue_api[0].email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    prevent_destroy = false

    ignore_changes = [
      # Ignore changes that don't require recreation
      template[0].annotations,
    ]

    create_before_destroy = true
  }

  depends_on = [google_project_service.apis]
}

# IAM for public access to enqueue API
resource "google_cloud_run_v2_service_iam_binding" "enqueue_api_invoker" {
  count    = var.enable_pipeline_client ? 1 : 0
  location = google_cloud_run_v2_service.enqueue_api[0].location
  name     = google_cloud_run_v2_service.enqueue_api[0].name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# Update the original Pub/Sub subscription with push config after Cloud Run service exists
resource "null_resource" "configure_pubsub_push" {
  count = var.enable_pipeline_client ? 1 : 0
  provisioner "local-exec" {
    command = "gcloud pubsub subscriptions update race-jobs-sub-${var.environment} --push-endpoint=${google_cloud_run_v2_service.enqueue_api[0].uri}/webhook --push-auth-service-account=${google_service_account.pubsub_invoker[0].email} --project=${var.project_id}"
  }

  depends_on = [
    google_cloud_run_v2_service.enqueue_api,
    google_pubsub_subscription.race_jobs_sub,
    google_service_account.pubsub_invoker
  ]
}
