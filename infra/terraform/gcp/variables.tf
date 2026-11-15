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

variable "node_zones" {
  description = "Explicit worker zones in region."
  type        = list(string)
}

variable "subnet_cidr" {
  description = "Worker node IPv4 range."
  type        = string
  default     = "10.20.0.0/20"
}

variable "pods_cidr" {
  description = "Pod secondary IPv4 range."
  type        = string
  default     = "10.24.0.0/14"
}

variable "services_cidr" {
  description = "Service secondary IPv4 range."
  type        = string
  default     = "10.28.0.0/20"
}

variable "master_cidr" {
  description = "Unused /28 for the GKE control plane."
  type        = string
  default     = "172.16.0.0/28"
}

variable "kubernetes_version" {
  description = "Minimum REGULAR-channel GKE version; requires 1.36.4-gke.1469000 or newer."
  type        = string
}

variable "node_machine_type" {
  description = "GCE worker machine type."
  type        = string
  default     = "e2-standard-2"
}

variable "node_count" {
  description = "Total workers, a positive multiple of the number of node_zones."
  type        = number
  default     = 2
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

variable "database_password" {
  description = "Initial database owner password; supply through TF_VAR_database_password."
  type        = string
  sensitive   = true
}

variable "deletion_protection" {
  description = "Protect the cluster and database from accidental deletion."
  type        = bool
  default     = true
}
