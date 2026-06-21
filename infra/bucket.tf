# Google Cloud Storage bucket for sv-data
resource "google_storage_bucket" "sv_data" {
  name     = "${var.project_id}-sv-data-${var.environment}"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true
  force_destroy               = !(var.environment == "prod" && var.prevent_destroy_prod)

  versioning {
    enabled = true
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "OPTIONS"]
    response_header = ["*"]
    max_age_seconds = 3600
  }

  lifecycle_rule {
    condition {
      age            = 90
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

  lifecycle_rule {
    condition {
      age            = 30
      matches_prefix = ["artifacts/"]
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age            = 7
      matches_prefix = ["checkpoints/"]
    }
    action {
      type = "Delete"
    }
  }

  # Prevent accidental deletion and ignore certain changes
  lifecycle {
    prevent_destroy = true
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
    "artifacts/",
    "checkpoints/",
  ])

  name    = each.value
  bucket  = google_storage_bucket.sv_data.name
  content = " " # Empty content to create folder structure
}

# Public static frontend reads are limited to published race data.
# Drafts, retired versions, artifacts, and checkpoints remain private.
resource "google_storage_bucket_iam_member" "published_races_public_reader" {
  bucket = google_storage_bucket.sv_data.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"

  condition {
    title       = "published-races-public-read"
    description = "Allow public reads only for objects under races/."
    expression  = "resource.name.startsWith(\"projects/_/buckets/${google_storage_bucket.sv_data.name}/objects/races/\")"
  }
}
