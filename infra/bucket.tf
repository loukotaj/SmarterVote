# Google Cloud Storage bucket for sv-data
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
  
  lifecycle_rule {
    condition {
      age = 30
      matches_storage_class = ["STANDARD"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

# Create folder structure (objects with trailing slashes)
resource "google_storage_bucket_object" "folders" {
  for_each = toset([
    "raw/",
    "norm/", 
    "out/",
    "arb/"
  ])
  
  name   = each.value
  bucket = google_storage_bucket.sv_data.name
  content = " "  # Empty content to create folder structure
}
