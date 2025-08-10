# Persistent storage for ChromaDB vector database
resource "google_storage_bucket" "chroma_storage" {
  name          = "${var.project_id}-chroma-${var.environment}"
  location      = var.region
  force_destroy = var.environment == "dev" # Only allow force destroy in dev

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = var.environment == "prod" ? 365 : 90 # Keep data longer in prod
    }
    action {
      type = "Delete"
    }
  }

  versioning {
    enabled = var.environment == "prod" # Enable versioning in production
  }

  labels = {
    component   = "vector-database"
    environment = var.environment
    purpose     = "chroma-persistence"
  }
}

# Grant access to the race worker service account
resource "google_storage_bucket_iam_member" "chroma_storage_race_worker" {
  bucket = google_storage_bucket.chroma_storage.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.race_worker.email}"
}

# Create a persistent disk for local ChromaDB storage in Cloud Run
resource "google_compute_disk" "chroma_disk" {
  name = "chroma-disk-${var.environment}"
  type = "pd-ssd"
  zone = "${var.region}-a"
  size = var.environment == "prod" ? 100 : 20 # GB

  labels = {
    component   = "vector-database"
    environment = var.environment
    purpose     = "chroma-local-storage"
  }
}
