Start Development Environmentterraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
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

# Include all infrastructure components
# Note: In a real setup, these would be separate modules
# For now, we're including them directly

# Storage (sv-data bucket)
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
}

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

# Service accounts
resource "google_service_account" "race_worker" {
  account_id   = "race-worker"
  display_name = "Race Processing Worker"
  description  = "Service account for Cloud Run race processing jobs"
}

# Basic IAM
resource "google_project_iam_member" "race_worker_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.race_worker.email}"
}

# Pub/Sub topic for race jobs
resource "google_pubsub_topic" "race_jobs" {
  name = "race-jobs"
  
  depends_on = [google_project_service.apis]
}

# Outputs
output "bucket_name" {
  description = "Name of the sv-data bucket"
  value       = google_storage_bucket.sv_data.name
}

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "pubsub_topic" {
  description = "Pub/Sub topic for race jobs"
  value       = google_pubsub_topic.race_jobs.name
}
