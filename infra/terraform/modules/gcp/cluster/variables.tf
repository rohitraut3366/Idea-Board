variable "name" {
  description = "GKE cluster name; keep at most 24 characters for the node service account."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.name))
    error_message = "Use 3 to 24 lowercase letters, digits, or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP cluster region."
  type        = string
}

variable "node_zones" {
  description = "Explicit worker zones; node_count is the total across these zones."
  type        = list(string)

  validation {
    condition     = length(var.node_zones) > 0 && length(distinct(var.node_zones)) == length(var.node_zones)
    error_message = "Provide at least one distinct worker zone."
  }
}

variable "network_id" {
  description = "VPC resource ID."
  type        = string
}

variable "subnetwork_id" {
  description = "Worker subnet resource ID."
  type        = string
}

variable "pods_range_name" {
  description = "Secondary subnet range for pods."
  type        = string
}

variable "services_range_name" {
  description = "Secondary subnet range for services."
  type        = string
}

variable "master_cidr" {
  description = "Unused /28 for the private GKE control plane."
  type        = string
}

variable "kubernetes_version" {
  description = "Minimum REGULAR-channel GKE version; requires 1.36.4-gke.1469000 or newer."
  type        = string
}

variable "node_machine_type" {
  description = "GCE machine type for workers."
  type        = string
  default     = "e2-standard-2"
}

variable "node_count" {
  description = "Total fixed number of worker nodes, distributed across node_zones."
  type        = number
  default     = 2

  validation {
    condition     = var.node_count >= 1 && floor(var.node_count) == var.node_count
    error_message = "node_count must be a positive integer."
  }
}

variable "deletion_protection" {
  description = "Block accidental cluster deletion."
  type        = bool
  default     = true
}
