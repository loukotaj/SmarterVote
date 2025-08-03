terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (dev/prod)"
  type        = string
  default     = "dev"
}

# API Keys (from secrets.tfvars)
variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API Key"
  type        = string
  sensitive   = true
}

variable "grok_api_key" {
  description = "Grok API Key"
  type        = string
  sensitive   = true
}

variable "google_search_api_key" {
  description = "Google Custom Search API Key"
  type        = string
  sensitive   = true
}

variable "google_search_cx" {
  description = "Google Custom Search Engine ID"
  type        = string
  sensitive   = true
}

# Data sources
data "google_project" "project" {
  project_id = var.project_id
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "customsearch.googleapis.com"
  ])

  service                    = each.value
  disable_dependent_services = true
}

# Random ID for unique resource names
resource "random_id" "suffix" {
  byte_length = 4
}

#==============================================
# STORAGE RESOURCES
#==============================================

# Google Cloud Storage bucket for sv-data
resource "google_storage_bucket" "sv_data" {
  name     = "${var.project_id}-sv-data"
  location = var.region
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 30
      matches_storage_class = ["STANDARD"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  depends_on = [google_project_service.apis]
}

# Create folder structure (objects with trailing slashes)
resource "google_storage_bucket_object" "folders" {
  for_each = toset([
    "raw/",
    "norm/", 
    "out/",
    "arb/"
  ])
  
  name   = each.value
  bucket = google_storage_bucket.sv_data.name
  content = " "  # Empty content to create folder structure
}

#==============================================
# SECRET MANAGER RESOURCES
#==============================================

# Secret Manager for API keys
resource "google_secret_manager_secret" "openai_key" {
  secret_id = "openai-api-key"
  
  replication {
    auto {}
  }
  
  depends_on = [google_project_service.apis]
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
  
  depends_on = [google_project_service.apis]
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
  
  depends_on = [google_project_service.apis]
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
  
  depends_on = [google_project_service.apis]
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
  
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "google_search_cx" {
  secret = google_secret_manager_secret.google_search_cx.id
  secret_data = var.google_search_cx
}

#==============================================
# SERVICE ACCOUNTS
#==============================================

# Service account for enqueue API
resource "google_service_account" "enqueue_api" {
  account_id   = "enqueue-api"
  display_name = "Enqueue API Service Account"
  description  = "Service account for the enqueue API Cloud Run service"
}

# Service account for race worker jobs
resource "google_service_account" "race_worker" {
  account_id   = "race-worker"
  display_name = "Race Processing Worker"
  description  = "Service account for Cloud Run race processing jobs"
}

# Service account for Pub/Sub invoker
resource "google_service_account" "pubsub_invoker" {
  account_id   = "pubsub-invoker"
  display_name = "Pub/Sub Invoker"
  description  = "Service account for Pub/Sub to invoke Cloud Run services"
}

#==============================================
# IAM BINDINGS
#==============================================

# Race worker permissions
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

resource "google_project_iam_member" "race_worker_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.race_worker.email}"
}

# Enqueue API permissions
resource "google_project_iam_member" "enqueue_api_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.enqueue_api.email}"
}

resource "google_project_iam_member" "enqueue_api_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.enqueue_api.email}"
}

# Pub/Sub invoker permissions
resource "google_project_iam_member" "pubsub_invoker_run" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

#==============================================
# PUB/SUB RESOURCES
#==============================================

# Pub/Sub topic for race processing jobs
resource "google_pubsub_topic" "race_jobs" {
  name = "race-jobs"
  
  message_retention_duration = "86400s"  # 24 hours
  
  depends_on = [google_project_service.apis]
}

# Dead letter queue for failed jobs
resource "google_pubsub_topic" "race_jobs_dlq" {
  name = "race-jobs-dlq"
  
  message_retention_duration = "604800s"  # 7 days
  
  depends_on = [google_project_service.apis]
}

# Pub/Sub subscription for race processing
resource "google_pubsub_subscription" "race_jobs_sub" {
  name  = "race-jobs-sub"
  topic = google_pubsub_topic.race_jobs.name
  
  ack_deadline_seconds = 600  # 10 minutes
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.race_jobs_dlq.id
    max_delivery_attempts = 5
  }
  
  # Note: Push config will be added after Cloud Run service is created
}

resource "google_pubsub_subscription" "race_jobs_dlq_sub" {
  name  = "race-jobs-dlq-sub"
  topic = google_pubsub_topic.race_jobs_dlq.name
  
  # Manual acknowledgment for investigation
  ack_deadline_seconds = 600
}

#==============================================
# CLOUD RUN JOB
#==============================================

# Cloud Run Job for race processing pipeline
resource "google_cloud_run_v2_job" "race_worker" {
  name     = "race-worker"
  location = var.region

  template {
    template {
      containers {
        image = "gcr.io/${var.project_id}/smartervote-pipeline:latest"
        
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        
        env {
          name  = "BUCKET_NAME"
          value = google_storage_bucket.sv_data.name
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
        
        resources {
          limits = {
            cpu    = "2000m"
            memory = "4Gi"
          }
        }
      }
      
      service_account = google_service_account.race_worker.email
      max_retries = 3
      task_count = 1
      parallelism = 1
      task_timeout = "3600s"  # 1 hour
    }
  }

  depends_on = [google_project_service.apis]
}

#==============================================
# CLOUD RUN SERVICE
#==============================================

# Cloud Run Service for enqueue API
resource "google_cloud_run_v2_service" "enqueue_api" {
  name     = "enqueue-api"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/smartervote-enqueue-api:latest"
      
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.race_jobs.name
      }
      
      env {
        name  = "CLOUD_RUN_JOB"
        value = google_cloud_run_v2_job.race_worker.name
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
    
    service_account = google_service_account.enqueue_api.email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

# IAM for public access to enqueue API
resource "google_cloud_run_v2_service_iam_binding" "enqueue_api_invoker" {
  location = google_cloud_run_v2_service.enqueue_api.location
  name     = google_cloud_run_v2_service.enqueue_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# Update Pub/Sub subscription with push config after service is created
resource "google_pubsub_subscription" "race_jobs_sub_push" {
  name  = "race-jobs-sub-push"
  topic = google_pubsub_topic.race_jobs.name
  
  ack_deadline_seconds = 600  # 10 minutes
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.race_jobs_dlq.id
    max_delivery_attempts = 5
  }
  
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.enqueue_api.uri}/webhook"
    
    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
    }
  }
}

#==============================================
# CLOUD SCHEDULER
#==============================================

# Cloud Scheduler job to trigger race processing
resource "google_cloud_scheduler_job" "daily_race_check" {
  name        = "daily-race-check"
  description = "Daily job to check for new races to process"
  schedule    = "0 6 * * *"  # 6 AM daily
  time_zone   = "America/New_York"
  region      = var.region

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.enqueue_api.uri}/trigger"
    
    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
    }
  }

  depends_on = [google_project_service.apis]
}

#==============================================
# OUTPUTS
#==============================================

output "bucket_name" {
  description = "Name of the sv-data bucket"
  value       = google_storage_bucket.sv_data.name
}

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP Region"
  value       = var.region
}

output "pubsub_topic" {
  description = "Pub/Sub topic for race jobs"
  value       = google_pubsub_topic.race_jobs.name
}

output "enqueue_api_url" {
  description = "URL of the enqueue API service"
  value       = google_cloud_run_v2_service.enqueue_api.uri
}

output "race_worker_job" {
  description = "Name of the race worker Cloud Run job"
  value       = google_cloud_run_v2_job.race_worker.name
}
