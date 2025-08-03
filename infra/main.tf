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

# Include all infrastructure modules
module "storage" {
  source = "./bucket.tf"
}

module "pubsub" {
  source = "./pubsub.tf"
}

module "secrets" {
  source = "./secrets.tf"
}

module "cloud_run" {
  source = "./run-service.tf"
}

module "scheduler" {
  source = "./scheduler.tf"
}
