variable "name" {
  description = "Name prefix for the controller IAM role."
  type        = string
}

variable "region" {
  description = "Region of the existing EKS cluster."
  type        = string
}

variable "cluster_name" {
  description = "Existing EKS cluster that will run the controller."
  type        = string
}

variable "vpc_id" {
  description = "VPC of the existing EKS cluster."
  type        = string
}
