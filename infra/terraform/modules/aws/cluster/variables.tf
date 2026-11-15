variable "name" {
  description = "EKS cluster name."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets across at least two availability zones."
  type        = list(string)
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version supported in the selected region."
  type        = string
}

variable "admin_role_arn" {
  description = "Existing IAM role granted Kubernetes cluster administration."
  type        = string
}

variable "node_instance_type" {
  description = "x86_64 EC2 instance type for worker nodes."
  type        = string
  default     = "c7i-flex.large"
}

variable "node_count" {
  description = "Fixed worker count; increase this for capacity tests."
  type        = number
  default     = 2

  validation {
    condition     = var.node_count >= 1 && floor(var.node_count) == var.node_count
    error_message = "node_count must be a positive integer."
  }
}
