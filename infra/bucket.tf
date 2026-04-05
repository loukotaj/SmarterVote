# Google Cloud Storage bucket for sv-data
resource "google_storage_bucket" "sv_data" {
  name     = "${var.project_id}-sv-data-${var.environment}"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
      matches_prefix = ["retired/"]
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age                   = 60
      matches_storage_class = ["STANDARD"]
      matches_prefix        = ["retired/"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  # Prevent accidental deletion and ignore certain changes
  lifecycle {
    prevent_destroy = false
    ignore_changes = [
      # Ignore changes to labels that might be managed externally
      labels,
    ]
  }

  labels = local.storage_labels

  depends_on = [google_project_service.apis]
}

# Create folder structure for published data
resource "google_storage_bucket_object" "folders" {
  for_each = toset([
    "races/",
    "drafts/",
    "retired/",
  ])

  name    = each.value
  bucket  = google_storage_bucket.sv_data.name
  content = " " # Empty content to create folder structure
}
