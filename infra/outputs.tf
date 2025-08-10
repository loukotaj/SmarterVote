# Terraform outputs for SmarterVote infrastructure

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP Region"
  value       = var.region
}

output "environment" {
  description = "Environment (dev/staging/prod)"
  value       = var.environment
}

output "app_version" {
  description = "Application version deployed"
  value       = var.app_version
}

output "terraform_state_bucket" {
  description = "Terraform state bucket name"
  value       = google_storage_bucket.terraform_state.name
  sensitive   = false
}

# Storage
output "bucket_name" {
  description = "Name of the sv-data bucket"
  value       = google_storage_bucket.sv_data.name
}

output "chroma_bucket_name" {
  description = "Name of the ChromaDB storage bucket"
  value       = google_storage_bucket.chroma_storage.name
}

output "chroma_disk_name" {
  description = "Name of the ChromaDB persistent disk"
  value       = google_compute_disk.chroma_disk.name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository for container images"
  value       = google_artifact_registry_repository.smartervote.name
}

output "container_registry_url" {
  description = "Base URL for container images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.smartervote.repository_id}"
}

# Pub/Sub
output "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic for race jobs"
  value       = google_pubsub_topic.race_jobs.name
}

output "pubsub_topic_id" {
  description = "Full ID of the Pub/Sub topic"
  value       = google_pubsub_topic.race_jobs.id
}

# Cloud Run Services
output "enqueue_api_url" {
  description = "URL of the enqueue API service"
  value       = google_cloud_run_v2_service.enqueue_api.uri
}

output "races_api_url" {
  description = "URL of the races API service"
  value       = google_cloud_run_v2_service.races_api.uri
}

# Cloud Run Jobs
output "race_worker_job_name" {
  description = "Name of the race worker Cloud Run job"
  value       = google_cloud_run_v2_job.race_worker.name
}

# Service Accounts
output "race_worker_email" {
  description = "Email of the race worker service account"
  value       = google_service_account.race_worker.email
}

output "enqueue_api_email" {
  description = "Email of the enqueue API service account"
  value       = google_service_account.enqueue_api.email
}

output "races_api_email" {
  description = "Email of the races API service account"
  value       = google_service_account.races_api.email
}

output "github_actions_email" {
  description = "Email of the GitHub Actions deployment service account"
  value       = google_service_account.github_actions.email
}
