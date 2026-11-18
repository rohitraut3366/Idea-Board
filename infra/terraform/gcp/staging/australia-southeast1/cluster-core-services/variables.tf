variable "name" {
  description = "Stack name, at most 24 characters, including environment."
  type        = string
}

variable "gitops_revision" {
  description = "Git branch, tag, or commit used by the cluster services root Application."
  type        = string
  default     = "master"
}

variable "project_id" {
  description = "Existing GCP project with billing enabled."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
}

variable "cluster_name" {
  description = "Cluster name supplied by the cluster Terragrunt dependency."
  type        = string
}
