# One-shot Cloud Run Job for durable race processing. Each execution receives a
# QUEUE_ITEM_ID override from races-api and runs the shared pipeline worker once.
resource "google_service_account" "pipeline_job" {
  project      = var.project_id
  account_id   = "pipeline-job-${var.environment}"
  display_name = "SmarterVote Pipeline Job SA (${var.environment})"
}

resource "google_project_iam_member" "pipeline_job_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.pipeline_job.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_job_storage" {
  bucket = google_storage_bucket.sv_data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline_job.email}"
}

# Secret access is granted per secret, not project-wide.
#
# This was a single project-level `roles/secretmanager.secretAccessor` binding,
# which let the pipeline job read every secret in the project — including
# `admin-api-key`, `stripe-secret-key`, `stripe-webhook-secret`, and the
# Cloudflare analytics token, none of which it has any reason to touch. The
# races-api service account already had the per-secret treatment; the job was
# missed in that pass.
#
# The four below are exactly the secrets the job's container declares as
# `secret_key_ref` env vars. Adding a fifth env secret means adding a binding
# here — the deploy fails loudly on a missing one, which is the intended
# tradeoff against a blanket grant that can never fail.
locals {
  pipeline_job_secret_ids = {
    openrouter = google_secret_manager_secret.openrouter_key.secret_id
    serper     = google_secret_manager_secret.serper_key.secret_id
    searlo     = google_secret_manager_secret.searlo_key.secret_id
    jina       = google_secret_manager_secret.jina_key.secret_id
  }
}

resource "google_secret_manager_secret_iam_member" "pipeline_job_secrets" {
  for_each = local.pipeline_job_secret_ids

  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pipeline_job.email}"
}

resource "google_cloud_run_v2_job" "pipeline" {
  name     = "pipeline-job-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.pipeline_job.email
      timeout         = "43200s"
      max_retries     = 0

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/smartervote-${var.environment}/pipeline-worker:${var.app_version}"

        env {
          name  = "WORKER_ONCE"
          value = "true"
        }
        env {
          name  = "WORKER_RUNNER"
          value = "cloud_run"
        }
        env {
          name  = "WORKER_CONCURRENCY"
          value = "1"
        }
        env {
          name  = "PIPELINE_MODE"
          value = "gcp"
        }
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "FIRESTORE_PROJECT"
          value = var.project_id
        }
        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.sv_data.name
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
          name = "SERPER_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.serper_key.secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "SEARLO_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.searlo_key.secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "JINA_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.jina_key.secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }
    }
  }

  labels = local.pipeline_labels

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.pipeline_job_firestore,
    google_storage_bucket_iam_member.pipeline_job_storage,
    google_secret_manager_secret_iam_member.pipeline_job_secrets,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "races_api_pipeline_job_runner" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.pipeline.name
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = "serviceAccount:${google_service_account.races_api.email}"
}
