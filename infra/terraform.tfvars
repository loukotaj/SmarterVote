# SmarterVote Terraform Variables
# This file contains non-sensitive default values
# Sensitive values are in secrets.tfvars

# Environment Configuration
environment = "dev"
region      = "us-central1"

# Application Configuration
app_version = "latest"

# Development Settings
force_update         = false
prevent_destroy_prod = true

# Note: project_id and API keys are set in secrets.tfvars
# Copy secrets.tfvars.example to secrets.tfvars and fill in your values
