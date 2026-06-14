# ---------------------------------------------------------------------------
# Agent Cloud Function (gen2)
# Triggered by Firestore document creation in pipeline_queue/{item_id}
# Replaces the retired pipeline-client Cloud Run service for AI processing
# ---------------------------------------------------------------------------

# Upload the source zip to GCS so Cloud Functions can build from it.
# The zip is created by the CI workflow before `terraform apply` runs.
# Using the git SHA in the object name forces a rebuild on every deploy.
resource "google_storage_bucket_object" "agent_function_source" {
  count        = var.enable_agent_function ? 1 : 0
  name         = "functions/agent-source-${var.app_version}.zip"
  bucket       = google_storage_bucket.sv_data.name
  source       = "${path.module}/functions-agent-source.zip"
  content_type = "application/zip"

  lifecycle {
    create_before_destroy = true
  }
}

# Service account for the agent function
resource "google_service_account" "agent_function" {
  count        = var.enable_agent_function ? 1 : 0
  project      = var.project_id
  account_id   = "agent-function-${var.environment}"
  display_name = "SmarterVote Agent Cloud Function SA (${var.environment})"
}

# IAM roles for the agent function SA
resource "google_project_iam_member" "agent_function_firestore" {
  count   = var.enable_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent_function[0].email}"
}

resource "google_project_iam_member" "agent_function_gcs" {
  count   = var.enable_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.agent_function[0].email}"
}

resource "google_project_iam_member" "agent_function_secret" {
  count   = var.enable_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.agent_function[0].email}"
}

resource "google_project_iam_member" "agent_function_eventarc" {
  count   = var.enable_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.agent_function[0].email}"
}

resource "google_project_iam_member" "agent_function_run_invoker" {
  count   = var.enable_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.agent_function[0].email}"
}

# Cloud Functions service agent needs read access to the source object bucket
# to copy the uploaded zip into the internal gcf-v2-sources bucket.
resource "google_storage_bucket_iam_member" "gcf_admin_source_reader" {
  count  = var.enable_agent_function || var.enable_admin_agent_function ? 1 : 0
  bucket = google_storage_bucket.sv_data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:service-${data.google_project.project.number}@gcf-admin-robot.iam.gserviceaccount.com"
}

# Ensure Eventarc's Google-managed service agent has its required project role.
resource "google_project_iam_member" "eventarc_service_agent" {
  count   = var.enable_agent_function || var.enable_admin_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/eventarc.serviceAgent"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# Cloud Function v2 (backed by Cloud Run gen2)
resource "google_cloudfunctions2_function" "agent" {
  count    = var.enable_agent_function ? 1 : 0
  name     = "agent-${var.environment}"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python311"
    entry_point = "process_queue_item"
    source {
      storage_source {
        bucket = google_storage_bucket.sv_data.name
        object = google_storage_bucket_object.agent_function_source[0].name
      }
    }
    environment_variables = {
      # Force rebuild when source changes
      BUILD_ID = var.app_version
    }
  }

  service_config {
    max_instance_count = 10
    # Allow parallel CF invocations so multiple races can be processed simultaneously
    max_instance_request_concurrency = 1

    timeout_seconds  = 540 # Event-triggered Cloud Functions max timeout
    available_memory = "2Gi"
    available_cpu    = "2"

    service_account_email = google_service_account.agent_function[0].email

    environment_variables = {
      PROJECT_ID                = var.project_id
      FIRESTORE_PROJECT         = var.project_id
      GCS_BUCKET                = google_storage_bucket.sv_data.name
      STORAGE_MODE              = "gcp"
      ENVIRONMENT               = var.environment
      AGENT_DEADLINE_SECONDS    = "480"
      QUEUE_LEASE_SECONDS       = "180"
      QUEUE_LEASE_RENEW_SECONDS = "60"
    }

    secret_environment_variables {
      key        = "OPENROUTER_API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.openrouter_key.secret_id
      version    = "latest"
    }

    secret_environment_variables {
      key        = "SERPER_API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.serper_key.secret_id
      version    = "latest"
    }

  }

  # Firestore (Eventarc) trigger — fires on every new document in pipeline_queue
  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.firestore.document.v1.created"
    event_filters {
      attribute = "database"
      value     = "(default)"
    }
    event_filters {
      attribute = "document"
      value     = "pipeline_queue/{item_id}"
      operator  = "match-path-pattern"
    }
    service_account_email = google_service_account.agent_function[0].email
    retry_policy          = "RETRY_POLICY_RETRY"
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.agent_function_eventarc,
    google_project_iam_member.agent_function_run_invoker,
    google_project_iam_member.eventarc_service_agent,
    google_storage_bucket_iam_member.gcf_admin_source_reader,
    google_secret_manager_secret_version.openrouter_key,
  ]
}

# Allow Eventarc SA to invoke the Cloud Run service backing the function
data "google_project" "project" {
  project_id = var.project_id
}

resource "google_cloud_run_v2_service_iam_member" "agent_function_invoker" {
  count    = var.enable_agent_function ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.agent[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# Output the function URL for reference
output "agent_function_url" {
  description = "URL of the agent Cloud Function (not publicly invocable — Eventarc only)"
  value       = var.enable_agent_function ? google_cloudfunctions2_function.agent[0].service_config[0].uri : null
}
