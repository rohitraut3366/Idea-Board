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

variable "deletion_protection" {
  description = "Protect the cluster and database from accidental deletion."
  type        = bool
  default     = true
}

variable "state_bucket" {
  description = "Shared S3 bucket containing all Terraform project states."
  type        = string
}

variable "state_prefix" {
  description = "Repository-relative environment path, supplied by the project command."
  type        = string
}

variable "state_region" {
  description = "AWS region containing the state bucket, supplied by the project command."
  type        = string
}
