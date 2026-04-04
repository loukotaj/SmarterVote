# SmarterVote Terraform Variables
# This file contains non-sensitive default values
# Sensitive values are in secrets.tfvars

# Environment Configuration
environment = "dev"
region      = "us-central1"

# Development Settings
force_update           = false
prevent_destroy_prod   = true
enable_pipeline_client = true

# CORS (explicit origins required for Auth0 credential-mode requests)
allowed_origins = [
  "https://smarter.vote",
  "https://www.smarter.vote",
  "http://localhost:5173",
  "http://localhost:4173",
]

# Note: project_id and API keys are set in secrets.tfvars
# Copy secrets.tfvars.example to secrets.tfvars and fill in your values
