# Durable deployed admin agent, triggered by admin_agent_tasks document creation.

resource "google_storage_bucket_object" "admin_agent_function_source" {
  count        = var.enable_admin_agent_function ? 1 : 0
  name         = "functions/admin-agent-source-${var.app_version}.zip"
  bucket       = google_storage_bucket.sv_data.name
  source       = "${path.module}/functions-admin-agent-source.zip"
  content_type = "application/zip"

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_service_account" "admin_agent_function" {
  count        = var.enable_admin_agent_function ? 1 : 0
  project      = var.project_id
  account_id   = "admin-agent-${var.environment}"
  display_name = "SmarterVote Admin Agent Function SA (${var.environment})"
}

resource "google_project_iam_member" "admin_agent_firestore" {
  count   = var.enable_admin_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.admin_agent_function[0].email}"
}

resource "google_project_iam_member" "admin_agent_eventarc" {
  count   = var.enable_admin_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.admin_agent_function[0].email}"
}

resource "google_project_iam_member" "admin_agent_run_invoker" {
  count   = var.enable_admin_agent_function ? 1 : 0
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.admin_agent_function[0].email}"
}

resource "google_secret_manager_secret_iam_member" "admin_agent_openrouter" {
  count     = var.enable_admin_agent_function ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.openrouter_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.admin_agent_function[0].email}"
}

resource "google_secret_manager_secret_iam_member" "admin_agent_admin_key" {
  count     = var.enable_admin_agent_function ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.admin_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.admin_agent_function[0].email}"
}

resource "google_cloudfunctions2_function" "admin_agent" {
  count    = var.enable_admin_agent_function ? 1 : 0
  name     = "admin-agent-${var.environment}"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python311"
    entry_point = "process_admin_agent_task"
    source {
      storage_source {
        bucket = google_storage_bucket.sv_data.name
        object = google_storage_bucket_object.admin_agent_function_source[0].name
      }
    }
    environment_variables = {
      BUILD_ID = var.app_version
    }
  }

  service_config {
    max_instance_count               = 3
    max_instance_request_concurrency = 1
    timeout_seconds                  = 540
    available_memory                 = "1Gi"
    available_cpu                    = "1"
    service_account_email            = google_service_account.admin_agent_function[0].email

    environment_variables = {
      PROJECT_ID                    = var.project_id
      FIRESTORE_PROJECT             = var.project_id
      RACES_API_URL                 = google_cloud_run_v2_service.races_api.uri
      ADMIN_AGENT_DEADLINE_SECONDS  = "450"
      ADMIN_AGENT_MAX_ITERATIONS    = "40"
      ADMIN_AGENT_MAX_CONTINUATIONS = "8"
      ADMIN_AGENT_MAX_TOTAL_TOKENS  = "200000"
      ADMIN_AGENT_MAX_OUTPUT_TOKENS = "4096"
      ADMIN_AGENT_MAX_COST_USD      = "5.0"
    }

    secret_environment_variables {
      key        = "OPENROUTER_API_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.openrouter_key.secret_id
      version    = "latest"
    }

    dynamic "secret_environment_variables" {
      for_each = var.admin_api_key != "" ? ["admin_key"] : []
      content {
        key        = "ADMIN_API_KEY"
        project_id = var.project_id
        secret     = google_secret_manager_secret.admin_api_key.secret_id
        version    = "latest"
      }
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.firestore.document.v1.created"
    event_filters {
      attribute = "database"
      value     = "(default)"
    }
    event_filters {
      attribute = "document"
      value     = "admin_agent_tasks/{task_id}"
      operator  = "match-path-pattern"
    }
    service_account_email = google_service_account.admin_agent_function[0].email
    retry_policy          = "RETRY_POLICY_RETRY"
  }

  depends_on = [
    google_project_iam_member.admin_agent_firestore,
    google_project_iam_member.admin_agent_eventarc,
    google_project_iam_member.admin_agent_run_invoker,
    google_project_iam_member.eventarc_service_agent,
    google_storage_bucket_iam_member.gcf_admin_source_reader,
    google_secret_manager_secret_iam_member.admin_agent_openrouter,
    google_secret_manager_secret_iam_member.admin_agent_admin_key,
    google_secret_manager_secret_version.openrouter_key,
    google_secret_manager_secret_version.admin_api_key,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "admin_agent_function_invoker" {
  count    = var.enable_admin_agent_function ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.admin_agent[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}
