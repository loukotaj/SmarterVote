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

variable "enable_admin_agent_function" {
  description = "Enable the durable Firestore-triggered deployed admin agent"
  type        = bool
  default     = true
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

variable "cloudflare_analytics_api_token" {
  description = "Read-only Cloudflare API token for Web Analytics GraphQL queries"
  type        = string
  sensitive   = true
  default     = ""
}

variable "cloudflare_analytics_account_tag" {
  description = "Cloudflare account ID containing the Web Analytics site"
  type        = string
  default     = ""
}

variable "cloudflare_analytics_site_tag" {
  description = "Cloudflare Web Analytics site token used to filter GraphQL data"
  type        = string
  default     = ""
}

variable "create_firestore_database" {
  description = "Set to true only on first deploy — requires Owner/Editor. Leave false if the (default) Firestore database already exists."
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = "GCP Billing Account ID. If empty, the budget alert resource is not created."
  type        = string
  default     = ""
}

variable "enable_billing_export" {
  description = <<-EOT
    Create the BigQuery dataset + IAM that receive the Cloud Billing export
    (the export toggle itself is enabled once in the Console).
    NOTE: requires the CI/CD deploy service account to have BigQuery dataset
    create permission (e.g. roles/bigquery.admin). Until that role is granted,
    leave this false or the deploy fails on dataset creation.
  EOT
  type        = bool
  default     = false
}

variable "bigquery_location" {
  description = "Location for the billing-export BigQuery dataset (multi-region recommended, e.g. US)."
  type        = string
  default     = "US"
}

variable "developer_gcp_identities" {
  description = "List of developer GCP emails (e.g. user:email@example.com) allowed to impersonate service accounts locally"
  type        = list(string)
  default     = []
}
