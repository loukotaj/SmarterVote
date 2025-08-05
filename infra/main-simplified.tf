# Simplified Terraform configuration for deploying races-api and enqueue-api services
# Removes pipeline processing, scheduler, and other unnecessary components

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

#==============================================
# VARIABLES
#==============================================

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
  description = "Environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

#==============================================
# ENABLE REQUIRED APIS
#==============================================

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  service                    = each.value
  disable_dependent_services = true
}

#==============================================
# STORAGE BUCKET FOR PUBLISHED DATA
#==============================================

resource "google_storage_bucket" "published_data" {
  name     = "${var.project_id}-published-data-${var.environment}"
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

  depends_on = [google_project_service.apis]
}

#==============================================
# SERVICE ACCOUNTS
#==============================================

resource "google_service_account" "enqueue_api" {
  account_id   = "enqueue-api-${var.environment}"
  display_name = "Enqueue API Service Account"
  description  = "Service account for the enqueue API Cloud Run service"
}

resource "google_service_account" "races_api" {
  account_id   = "races-api-${var.environment}"
  display_name = "Races API Service Account"
  description  = "Service account for the races API Cloud Run service"
}

#==============================================
# IAM PERMISSIONS
#==============================================

# Enqueue API permissions - needs to publish to Pub/Sub
resource "google_project_iam_member" "enqueue_api_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.enqueue_api.email}"
}

# Races API permissions - needs to read from storage bucket
resource "google_project_iam_member" "races_api_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.races_api.email}"
}

#==============================================
# PUB/SUB TOPIC FOR JOB QUEUE
#==============================================

resource "google_pubsub_topic" "race_jobs" {
  name = "race-jobs-${var.environment}"

  message_retention_duration = "86400s" # 24 hours

  depends_on = [google_project_service.apis]
}

#==============================================
# CLOUD RUN SERVICES
#==============================================

# Enqueue API Service
resource "google_cloud_run_v2_service" "enqueue_api" {
  name     = "enqueue-api-${var.environment}"
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

# Races API Service
resource "google_cloud_run_v2_service" "races_api" {
  name     = "races-api-${var.environment}"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/smartervote-races-api:latest"

      env {
        name  = "DATA_DIR"
        value = "/app/data"
      }

      env {
        name  = "BUCKET_NAME"
        value = google_storage_bucket.published_data.name
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

    service_account = google_service_account.races_api.email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

#==============================================
# IAM FOR PUBLIC ACCESS
#==============================================

# Public access to enqueue API
resource "google_cloud_run_v2_service_iam_binding" "enqueue_api_invoker" {
  location = google_cloud_run_v2_service.enqueue_api.location
  name     = google_cloud_run_v2_service.enqueue_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# Public access to races API
resource "google_cloud_run_v2_service_iam_binding" "races_api_invoker" {
  location = google_cloud_run_v2_service.races_api.location
  name     = google_cloud_run_v2_service.races_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

#==============================================
# OUTPUTS
#==============================================

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP Region"
  value       = var.region
}

output "environment" {
  description = "Environment"
  value       = var.environment
}

output "published_data_bucket" {
  description = "Name of the published data bucket"
  value       = google_storage_bucket.published_data.name
}

output "pubsub_topic" {
  description = "Pub/Sub topic for race jobs"
  value       = google_pubsub_topic.race_jobs.name
}

output "enqueue_api_url" {
  description = "URL of the enqueue API service"
  value       = google_cloud_run_v2_service.enqueue_api.uri
}

output "races_api_url" {
  description = "URL of the races API service"
  value       = google_cloud_run_v2_service.races_api.uri
}
