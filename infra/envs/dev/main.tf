terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }

  backend "gcs" {
    bucket = "smartervote-terraform-state"
    prefix = "terraform/dev"
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
  description = "Environment name"
  type        = string
  default     = "dev"
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
    "firestore.googleapis.com",
    "cloudbuild.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  service                    = each.value
  disable_dependent_services = true
}

# Cloud Storage bucket for data
resource "google_storage_bucket" "data_bucket" {
  name     = "${var.project_id}-smartervote-data"
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
}

# Pub/Sub topic for race processing
resource "google_pubsub_topic" "race_processing" {
  name = "race-processing"
}

# Pub/Sub subscription
resource "google_pubsub_subscription" "race_processing_sub" {
  name  = "race-processing-sub"
  topic = google_pubsub_topic.race_processing.name
  
  ack_deadline_seconds = 600
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }
}

# Cloud Run service for enqueue API
resource "google_cloud_run_service" "enqueue_api" {
  name     = "smartervote-enqueue-api"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/smartervote-enqueue-api:latest"
        
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        
        env {
          name  = "PUBSUB_TOPIC"
          value = google_pubsub_topic.race_processing.name
        }
        
        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [google_project_service.apis]
}

# IAM for Cloud Run
resource "google_cloud_run_service_iam_binding" "enqueue_api_invoker" {
  location = google_cloud_run_service.enqueue_api.location
  service  = google_cloud_run_service.enqueue_api.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# Outputs
output "enqueue_api_url" {
  description = "URL of the enqueue API"
  value       = google_cloud_run_service.enqueue_api.status[0].url
}

output "data_bucket_name" {
  description = "Name of the data storage bucket"
  value       = google_storage_bucket.data_bucket.name
}

output "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic"
  value       = google_pubsub_topic.race_processing.name
}
