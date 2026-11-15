variable "name" {
  description = "Prefix for network resources."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
}

variable "subnet_cidr" {
  description = "Primary IPv4 range for worker nodes."
  type        = string
}

variable "pods_cidr" {
  description = "Secondary IPv4 range for Kubernetes pods."
  type        = string
}

variable "services_cidr" {
  description = "Secondary IPv4 range for Kubernetes services."
  type        = string
}
