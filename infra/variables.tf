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
  description = "OpenAI API key for GPT-4o"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for Claude-3.5"
  type        = string
  sensitive   = true
}

variable "grok_api_key" {
  description = "Grok API key for X.AI"
  type        = string
  sensitive   = true
}

variable "google_search_api_key" {
  description = "Google Custom Search API key"
  type        = string
  sensitive   = true
}

variable "google_search_cx" {
  description = "Google Custom Search Engine ID"
  type        = string
  sensitive   = true
}
