# Secret Manager for API keys - all in same project
resource "google_secret_manager_secret" "openai_key" {
  project   = var.project_id
  secret_id = "openai-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "openai_key" {
  count       = var.openai_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.openai_key.id
  secret_data = var.openai_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "serper_key" {
  project   = var.project_id
  secret_id = "serper-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "serper_key" {
  count       = var.serper_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.serper_key.id
  secret_data = var.serper_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Optional review provider secrets
resource "google_secret_manager_secret" "anthropic_key" {
  count     = var.enable_pipeline_client ? 1 : 0
  project   = var.project_id
  secret_id = "anthropic-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_key" {
  count       = var.enable_pipeline_client && var.anthropic_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.anthropic_key[0].id
  secret_data = var.anthropic_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "gemini_key" {
  count     = var.enable_pipeline_client ? 1 : 0
  project   = var.project_id
  secret_id = "gemini-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gemini_key" {
  count       = var.enable_pipeline_client && var.gemini_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.gemini_key[0].id
  secret_data = var.gemini_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "xai_key" {
  count     = var.enable_pipeline_client ? 1 : 0
  project   = var.project_id
  secret_id = "xai-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "xai_key" {
  count       = var.enable_pipeline_client && var.xai_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.xai_key[0].id
  secret_data = var.xai_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Service accounts for the same project
resource "google_service_account" "race_worker" {
  count        = var.enable_pipeline_client ? 1 : 0
  project      = var.project_id
  account_id   = "race-worker-${var.environment}"
  display_name = "Race Worker Service Account"
  description  = "Service account for race processing pipeline"
}

resource "google_service_account" "enqueue_api" {
  count        = var.enable_pipeline_client ? 1 : 0
  project      = var.project_id
  account_id   = "enqueue-api-${var.environment}"
  display_name = "Enqueue API Service Account"
  description  = "Service account for enqueue API Cloud Run service"
}

resource "google_service_account" "races_api" {
  project      = var.project_id
  account_id   = "races-api-${var.environment}"
  display_name = "Races API Service Account"
  description  = "Service account for races API Cloud Run service"
}

resource "google_service_account" "pipeline_client" {
  count        = var.enable_pipeline_client ? 1 : 0
  project      = var.project_id
  account_id   = "pipeline-client-${var.environment}"
  display_name = "Pipeline Client Service Account"
  description  = "Service account for pipeline client Cloud Run service"
}

resource "google_service_account" "pubsub_invoker" {
  count        = var.enable_pipeline_client ? 1 : 0
  project      = var.project_id
  account_id   = "pubsub-invoker-${var.environment}"
  display_name = "Pub/Sub Invoker Service Account"
  description  = "Service account for Pub/Sub to invoke Cloud Run"
}

# GitHub Actions deployment service account
resource "google_service_account" "github_actions" {
  project      = var.project_id
  account_id   = "github-actions-${var.environment}"
  display_name = "GitHub Actions Deployment Service Account"
  description  = "Service account for GitHub Actions to deploy infrastructure and services"
}

# IAM bindings for race worker - all within same project (only when pipeline enabled)
resource "google_project_iam_member" "race_worker_storage" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.race_worker[0].email}"
}

resource "google_project_iam_member" "race_worker_secrets" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.race_worker[0].email}"
}

resource "google_project_iam_member" "race_worker_run_jobs" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.race_worker[0].email}"
}

resource "google_project_iam_member" "race_worker_pubsub" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.race_worker[0].email}"
}

resource "google_project_iam_member" "race_worker_artifact_registry" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.race_worker[0].email}"
}

# IAM bindings for enqueue API (only when pipeline enabled)
resource "google_project_iam_member" "enqueue_api_pubsub" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.enqueue_api[0].email}"
}

resource "google_project_iam_member" "enqueue_api_run_invoker" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.enqueue_api[0].email}"
}

resource "google_project_iam_member" "enqueue_api_run_developer" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.enqueue_api[0].email}"
}

resource "google_project_iam_member" "enqueue_api_artifact_registry" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.enqueue_api[0].email}"
}

# IAM bindings for races API
resource "google_project_iam_member" "races_api_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.races_api.email}"
}

resource "google_project_iam_member" "races_api_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.races_api.email}"
}

# IAM bindings for pipeline client (only when pipeline enabled)
resource "google_project_iam_member" "pipeline_client_storage" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.pipeline_client[0].email}"
}

resource "google_project_iam_member" "pipeline_client_secrets" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.pipeline_client[0].email}"
}

resource "google_project_iam_member" "pipeline_client_artifact_registry" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.pipeline_client[0].email}"
}

# IAM bindings for GitHub Actions deployment service account
resource "google_project_iam_member" "github_actions_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_cloud_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_storage" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_iam" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Custom role granting only the permissions needed to create/delete service accounts
# during Terraform apply (e.g., when enable_pipeline_client toggles between true/false)
resource "google_project_iam_custom_role" "sa_manager" {
  project     = var.project_id
  role_id     = "saManager_${var.environment}"
  title       = "Service Account Manager (${var.environment})"
  description = "Minimal role to create and delete service accounts for infrastructure management"
  permissions = [
    "iam.serviceAccounts.create",
    "iam.serviceAccounts.delete",
    "iam.serviceAccounts.get",
    "iam.serviceAccounts.list",
    "iam.serviceAccounts.update",
  ]
}

resource "google_project_iam_member" "github_actions_sa_admin" {
  project = var.project_id
  role    = google_project_iam_custom_role.sa_manager.id
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Allow GitHub Actions SA to read Secret Manager metadata for terraform plan/apply
resource "google_project_iam_member" "github_actions_secret_manager" {
  project = var.project_id
  role    = "roles/secretmanager.viewer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# IAM bindings for Pub/Sub invoker (only when pipeline enabled)
resource "google_project_iam_member" "pubsub_invoker_run" {
  count   = var.enable_pipeline_client ? 1 : 0
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pubsub_invoker[0].email}"
}
