# SmarterVote Infrastructure - Main Configuration
# Complete infrastructure deployment for corpus-first AI electoral analysis pipeline

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

# Container Registry for Docker images
resource "google_container_registry" "registry" {
  project  = var.project_id
  location = "US"

  depends_on = [google_project_service.apis]
}

# Artifact Registry for enhanced container management (recommended over GCR)
resource "google_artifact_registry_repository" "smartervote" {
  location      = var.region
  repository_id = "smartervote-${var.environment}"
  description   = "SmarterVote container images for ${var.environment} environment"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}
