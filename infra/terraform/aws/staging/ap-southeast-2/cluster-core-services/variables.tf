variable "name" {
  description = "Stack name, including environment, for example idea-board-staging."
  type        = string
}

variable "gitops_revision" {
  description = "Git branch, tag, or commit used by the cluster services root Application."
  type        = string
  default     = "master"
}

variable "external_secrets_values" {
  description = "Non-secret External Secrets overrides published to the cluster's generated values file."
  type        = any
  default     = {}
}

variable "region" {
  description = "AWS region."
  type        = string
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
