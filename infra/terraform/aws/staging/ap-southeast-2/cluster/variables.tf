variable "name" {
  description = "Stack name, including environment, for example idea-board-staging."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "kubernetes_version" {
  description = "Supported EKS Kubernetes version."
  type        = string
}

variable "admin_role_arn" {
  description = "Existing IAM role for Kubernetes administration."
  type        = string
}

variable "node_instance_type" {
  description = "x86_64 EC2 worker instance type."
  type        = string
  default     = "t3.medium"
}

variable "node_count" {
  description = "Fixed total number of worker nodes."
  type        = number
  default     = 2
}

variable "state_bucket" {
  description = "Bucket containing this environment's Terraform project states."
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
