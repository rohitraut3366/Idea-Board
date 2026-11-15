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

variable "subnet_cidr" {
  description = "Worker node IPv4 range."
  type        = string
  default     = "10.20.0.0/20"
}

variable "pods_cidr" {
  description = "Pod secondary IPv4 range."
  type        = string
  default     = "10.24.0.0/14"
}

variable "services_cidr" {
  description = "Service secondary IPv4 range."
  type        = string
  default     = "10.28.0.0/20"
}
