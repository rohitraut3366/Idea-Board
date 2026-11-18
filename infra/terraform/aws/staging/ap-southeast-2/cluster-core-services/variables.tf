variable "name" {
  description = "Stack name, including environment, for example idea-board-staging."
  type        = string
}

variable "gitops_revision" {
  description = "Git branch, tag, or commit used by the cluster services root Application."
  type        = string
  default     = "master"
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "cluster_name" {
  description = "Cluster name supplied by the cluster Terragrunt dependency."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID supplied by the networking Terragrunt dependency."
  type        = string
}
