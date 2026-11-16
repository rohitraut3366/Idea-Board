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

variable "state_bucket" {
  description = "Shared S3 bucket containing all Terraform project states."
  type        = string
}

variable "state_prefix" {
  description = "Repository-relative environment path, supplied by Terragrunt."
  type        = string
}

variable "state_region" {
  description = "AWS region containing the state bucket, supplied by Terragrunt."
  type        = string
}
