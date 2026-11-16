variable "name" {
  description = "Stack name, at most 24 characters."
  type        = string
}

variable "project_id" {
  description = "GCP project whose secrets External Secrets reads."
  type        = string
}

variable "cluster_name" {
  description = "Cluster receiving the generated Helm values."
  type        = string
}
