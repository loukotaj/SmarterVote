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

# ChromaDB Vector Database Configuration
variable "chroma_chunk_size" {
  description = "Word count per chunk for vector database"
  type        = number
  default     = 500
}

variable "chroma_chunk_overlap" {
  description = "Word overlap between chunks"
  type        = number
  default     = 50
}

variable "chroma_embedding_model" {
  description = "Sentence transformer model for embeddings"
  type        = string
  default     = "all-MiniLM-L6-v2"
}

variable "chroma_similarity_threshold" {
  description = "Minimum similarity score for search results"
  type        = number
  default     = 0.7
}

variable "chroma_max_results" {
  description = "Maximum search results to return"
  type        = number
  default     = 100
}

variable "chroma_persist_dir" {
  description = "Directory for ChromaDB persistence in containers"
  type        = string
  default     = "/app/data/chroma_db"
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
