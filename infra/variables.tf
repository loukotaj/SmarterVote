# Core Variables
variable "project_id" {
  description = "GCP Project ID - used across all resources"
  type        = string
}

variable "region" {
  description = "GCP Region for all resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

# API Keys for AI Services
variable "openrouter_api_key" {
  description = "OpenRouter API key for all LLM calls"
  type        = string
  sensitive   = true
  default     = ""
}

variable "serper_api_key" {
  description = "Serper.dev API key for web search"
  type        = string
  sensitive   = true
  default     = ""
}

# Deployment and versioning variables
variable "app_version" {
  description = "Application version for tracking updates"
  type        = string
  default     = "latest"
}

variable "force_update" {
  description = "Force update of Cloud Run services"
  type        = bool
  default     = false
}

variable "prevent_destroy_prod" {
  description = "Prevent destruction of resources in production"
  type        = bool
  default     = true
}

variable "auth0_domain" {
  description = "Auth0 domain for races-api admin authentication"
  type        = string
  default     = ""
}

variable "auth0_audience" {
  description = "Auth0 audience for races-api admin authentication"
  type        = string
  default     = ""
}

variable "allowed_origins" {
  description = "Allowed CORS origins for the optional legacy pipeline client"
  type        = list(string)
  default = [
    "https://smarter.vote",
    "https://www.smarter.vote",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
  ]
}

# Legacy Pipeline Client Deployment Toggle
# Keep false for normal production; the agent Cloud Function processes queue items.
variable "enable_pipeline_client" {
  description = "Enable the legacy pipeline client Cloud Run service for local/debug workflows"
  type        = bool
  default     = false
}

variable "enable_agent_function" {
  description = "Enable the agent Cloud Function (gen2) that processes pipeline_queue items via Eventarc"
  type        = bool
  default     = true
}

variable "pipeline_client_public_invoker" {
  description = "Allow unauthenticated Cloud Run invocations. Must be true for browser clients: CORS OPTIONS preflights carry no credentials so GCP-level IAM auth blocks them before the app can respond. Auth0 JWT handles application-layer auth."
  type        = bool
  default     = false # Override to true in tfvars for any deployment that serves browser clients
}

# Monitoring / alerting
variable "alert_email" {
  description = "Email address to receive GCP monitoring alerts. Leave empty to disable alert policies."
  type        = string
  default     = ""
}

variable "admin_api_key" {
  description = "Secret key that protects the /analytics/* endpoints on the races API"
  type        = string
  sensitive   = true
  default     = ""
}

variable "create_firestore_database" {
  description = "Set to true only on first deploy — requires Owner/Editor. Leave false if the (default) Firestore database already exists."
  type        = bool
  default     = false
}
