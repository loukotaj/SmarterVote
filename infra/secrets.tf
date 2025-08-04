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
  secret      = google_secret_manager_secret.openai_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "anthropic_key" {
  project   = var.project_id
  secret_id = "anthropic-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_key" {
  secret      = google_secret_manager_secret.anthropic_key.id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret" "grok_key" {
  project   = var.project_id
  secret_id = "grok-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "grok_key" {
  secret      = google_secret_manager_secret.grok_key.id
  secret_data = var.grok_api_key
}

# Google Custom Search API credentials
resource "google_secret_manager_secret" "google_search_key" {
  project   = var.project_id
  secret_id = "google-search-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "google_search_key" {
  secret      = google_secret_manager_secret.google_search_key.id
  secret_data = var.google_search_api_key
}

resource "google_secret_manager_secret" "google_search_cx" {
  project   = var.project_id
  secret_id = "google-search-cx-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "google_search_cx" {
  secret      = google_secret_manager_secret.google_search_cx.id
  secret_data = var.google_search_cx
}

# Service accounts for the same project
resource "google_service_account" "race_worker" {
  project      = var.project_id
  account_id   = "race-worker-${var.environment}"
  display_name = "Race Worker Service Account"
  description  = "Service account for race processing pipeline"
}

resource "google_service_account" "enqueue_api" {
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

resource "google_service_account" "pubsub_invoker" {
  project      = var.project_id
  account_id   = "pubsub-invoker-${var.environment}"
  display_name = "Pub/Sub Invoker Service Account"
  description  = "Service account for Pub/Sub to invoke Cloud Run"
}

# IAM bindings for race worker - all within same project
resource "google_project_iam_member" "race_worker_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.race_worker.email}"
}

resource "google_project_iam_member" "race_worker_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.race_worker.email}"
}

resource "google_project_iam_member" "race_worker_run_jobs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.race_worker.email}"
}

resource "google_project_iam_member" "race_worker_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.race_worker.email}"
}

# IAM bindings for enqueue API
resource "google_project_iam_member" "enqueue_api_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.enqueue_api.email}"
}

resource "google_project_iam_member" "enqueue_api_run_jobs" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.enqueue_api.email}"
}

# IAM bindings for races API
resource "google_project_iam_member" "races_api_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.races_api.email}"
}

# IAM bindings for Pub/Sub invoker
resource "google_project_iam_member" "pubsub_invoker_run" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}
