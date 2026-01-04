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

# Pub/Sub (only when pipeline_client enabled)
output "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic for race jobs"
  value       = var.enable_pipeline_client ? google_pubsub_topic.race_jobs[0].name : null
}

output "pubsub_topic_id" {
  description = "Full ID of the Pub/Sub topic"
  value       = var.enable_pipeline_client ? google_pubsub_topic.race_jobs[0].id : null
}

# Cloud Run Services
output "enqueue_api_url" {
  description = "URL of the enqueue API service"
  value       = var.enable_pipeline_client ? google_cloud_run_v2_service.enqueue_api[0].uri : null
}

output "races_api_url" {
  description = "URL of the races API service"
  value       = google_cloud_run_v2_service.races_api.uri
}

output "pipeline_client_url" {
  description = "URL of the pipeline client service"
  value       = var.enable_pipeline_client ? google_cloud_run_v2_service.pipeline_client[0].uri : null
}

# Cloud Run Jobs (only when pipeline_client enabled)
output "race_worker_job_name" {
  description = "Name of the race worker Cloud Run job"
  value       = var.enable_pipeline_client ? google_cloud_run_v2_job.race_worker[0].name : null
}

# Service Accounts
output "race_worker_email" {
  description = "Email of the race worker service account"
  value       = var.enable_pipeline_client ? google_service_account.race_worker[0].email : null
}

output "enqueue_api_email" {
  description = "Email of the enqueue API service account"
  value       = var.enable_pipeline_client ? google_service_account.enqueue_api[0].email : null
}

output "races_api_email" {
  description = "Email of the races API service account"
  value       = google_service_account.races_api.email
}

output "pipeline_client_email" {
  description = "Email of the pipeline client service account"
  value       = var.enable_pipeline_client ? google_service_account.pipeline_client[0].email : null
}

output "github_actions_email" {
  description = "Email of the GitHub Actions deployment service account"
  value       = google_service_account.github_actions.email
}
