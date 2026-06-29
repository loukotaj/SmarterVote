# BigQuery dataset that receives the Cloud Billing export.
#
# IMPORTANT: Creating this dataset does NOT turn the export on. The billing
# export toggle is billing-account scoped and Console-only — there is no
# Terraform or gcloud resource that enables it. After `terraform apply`, enable
# it once (takes ~2 minutes, then data lands ~24h later):
#
#   Cloud Console -> Billing -> Billing export -> BigQuery export
#     -> Edit settings -> Detailed usage cost
#     -> Project: ${var.project_id}, Dataset: billing_export -> Save
#
# Once enabled, the export creates a table named
#   gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID with dashes as underscores>
# which the races-api /pipeline/gcp-costs endpoint discovers automatically.

resource "google_bigquery_dataset" "billing_export" {
  count = var.enable_billing_export ? 1 : 0

  dataset_id    = "billing_export"
  friendly_name = "Cloud Billing export (${var.environment})"
  description   = "Destination for the Cloud Billing detailed usage cost export. Enable the export in the Cloud Console (billing-account scoped) — see billing-export.tf."
  location      = var.bigquery_location
  project       = var.project_id

  labels = local.storage_labels

  depends_on = [google_project_service.apis]
}

# Allow the races-api service account to read and query the billing export so the
# cost dashboard endpoint can aggregate GCP spend.
resource "google_bigquery_dataset_iam_member" "races_api_billing_viewer" {
  count = var.enable_billing_export ? 1 : 0

  dataset_id = google_bigquery_dataset.billing_export[0].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.races_api.email}"
}

# Querying BigQuery requires job-creation permission at the project level.
resource "google_project_iam_member" "races_api_bq_job_user" {
  count = var.enable_billing_export ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.races_api.email}"
}
