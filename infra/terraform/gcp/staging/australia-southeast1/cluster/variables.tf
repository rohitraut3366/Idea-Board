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

variable "network_id" {
  description = "Network ID supplied by the networking Terragrunt dependency."
  type        = string
}

variable "subnetwork_id" {
  description = "Subnetwork ID supplied by the networking Terragrunt dependency."
  type        = string
}

variable "pods_range_name" {
  description = "Pods range name supplied by the networking Terragrunt dependency."
  type        = string
}

variable "services_range_name" {
  description = "Services range name supplied by the networking Terragrunt dependency."
  type        = string
}
