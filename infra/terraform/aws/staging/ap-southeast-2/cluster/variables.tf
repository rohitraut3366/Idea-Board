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
  description = "Optional Kubernetes administrator role; defaults to the logged-in IAM role."
  type        = string
  default     = null
}

variable "node_instance_type" {
  description = "x86_64 EC2 worker instance type."
  type        = string
  default     = "c7i-flex.large"
}

variable "node_count" {
  description = "Fixed total number of worker nodes."
  type        = number
  default     = 2
}

variable "private_subnet_ids" {
  description = "Private subnet IDs supplied by the networking Terragrunt dependency."
  type        = list(string)
}
