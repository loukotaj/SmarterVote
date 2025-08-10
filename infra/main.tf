# SmarterVote Infrastructure - Main Configuration
# Complete infrastructure deployment for corpus-first AI electoral analysis pipeline

terraform {
  required_version = ">= 1.0"

  # Remote state backend for consistency and locking
  backend "gcs" {
    bucket = "smartervote-terraform-state"
    prefix = "terraform/state"
  }

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

# Common labels for all resources
locals {
  common_labels = {
    project     = "smartervote"
    environment = var.environment
    managed_by  = "terraform"
    version     = var.app_version != "" ? var.app_version : "unknown"
  }

  pipeline_labels = merge(local.common_labels, {
    component = "pipeline"
    service   = "race-processing"
  })

  api_labels = merge(local.common_labels, {
    component = "api"
  })

  storage_labels = merge(local.common_labels, {
    component = "storage"
  })
}

# Terraform state bucket (must be created first with local backend)
resource "google_storage_bucket" "terraform_state" {
  name          = "smartervote-terraform-state"
  location      = var.region
  force_destroy = false
  project       = var.project_id

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = false
  }

  labels = local.storage_labels

  depends_on = [google_project_service.apis]
}

# Enable required GCP APIs for the project
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "containerregistry.googleapis.com",
    "artifactregistry.googleapis.com",
    "customsearch.googleapis.com",
    "iam.googleapis.com"
  ])

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = true
}

# Artifact Registry for enhanced container management (recommended over GCR)
resource "google_artifact_registry_repository" "smartervote" {
  location      = var.region
  repository_id = "smartervote-${var.environment}"
  description   = "SmarterVote container images for ${var.environment} environment"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}
