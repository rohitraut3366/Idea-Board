variable "name" {
  description = "Stack name, at most 24 characters, including environment."
  type        = string
}

variable "project_id" {
  description = "Existing GCP project with billing enabled."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
}

variable "database_tier" {
  description = "Cloud SQL instance tier."
  type        = string
  default     = "db-custom-1-3840"
}

variable "database_storage_gb" {
  description = "Initial Cloud SQL storage in GiB."
  type        = number
  default     = 20
}

variable "database_regional" {
  description = "Enable a standby database in another zone."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Protect the cluster and database from accidental deletion."
  type        = bool
  default     = true
}

variable "network_id" {
  description = "Network ID supplied by the networking Terragrunt dependency."
  type        = string
}

variable "cluster_name" {
  description = "Cluster name supplied by the cluster Terragrunt dependency."
  type        = string
}
