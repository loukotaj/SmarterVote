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
variable "openai_api_key" {
  description = "OpenAI API key for GPT-4o/mini"
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

variable "anthropic_api_key" {
  description = "Anthropic API key for Claude review"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key for review"
  type        = string
  sensitive   = true
  default     = ""
}

variable "xai_api_key" {
  description = "xAI API key for Grok review"
  type        = string
  sensitive   = true
  default     = ""
}

# Deployment and versioning variables
variable "app_version" {
  description = "Application version for tracking updates"
  type        = string
  default     = ""
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
  description = "Auth0 domain for pipeline client authentication"
  type        = string
  default     = ""
}

variable "auth0_audience" {
  description = "Auth0 audience for pipeline client authentication"
  type        = string
  default     = ""
}

variable "allowed_origins" {
  description = "Allowed CORS origins for pipeline client"
  type        = list(string)
  default     = ["*"]
}

# Pipeline Client Deployment Toggle
# Set to true when ready to deploy pipeline processing to cloud
variable "enable_pipeline_client" {
  description = "Enable pipeline client cloud deployment (expensive - runs AI processing)"
  type        = bool
  default     = false
}

# Monitoring / alerting
variable "alert_email" {
  description = "Email address to receive GCP monitoring alerts. Leave empty to disable alert policies."
  type        = string
  default     = ""
}
