# Secret Manager for API keys
resource "google_secret_manager_secret" "openai_key" {
  secret_id = "openai-api-key"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "openai_key" {
  secret = google_secret_manager_secret.openai_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "anthropic_key" {
  secret_id = "anthropic-api-key"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "anthropic_key" {
  secret = google_secret_manager_secret.anthropic_key.id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret" "grok_key" {
  secret_id = "grok-api-key"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "grok_key" {
  secret = google_secret_manager_secret.grok_key.id
  secret_data = var.grok_api_key
}

# Google Custom Search API credentials
resource "google_secret_manager_secret" "google_search_key" {
  secret_id = "google-search-api-key"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "google_search_key" {
  secret = google_secret_manager_secret.google_search_key.id
  secret_data = var.google_search_api_key
}

resource "google_secret_manager_secret" "google_search_cx" {
  secret_id = "google-search-cx"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "google_search_cx" {
  secret = google_secret_manager_secret.google_search_cx.id
  secret_data = var.google_search_cx
}

# Service accounts
resource "google_service_account" "race_worker" {
  account_id   = "race-worker"
  display_name = "Race Processing Worker"
  description  = "Service account for Cloud Run race processing jobs"
}

resource "google_service_account" "enqueue_api" {
  account_id   = "enqueue-api"
  display_name = "Enqueue API Service"
  description  = "Service account for enqueue API Cloud Run service"
}

resource "google_service_account" "pubsub_invoker" {
  account_id   = "pubsub-invoker"
  display_name = "Pub/Sub Invoker"
  description  = "Service account for Pub/Sub to invoke Cloud Run services"
}

# IAM bindings for race worker
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

# IAM bindings for Pub/Sub invoker
resource "google_project_iam_member" "pubsub_invoker_run" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}
