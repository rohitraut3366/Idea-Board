variable "name" {
  description = "Stack name, including environment, for example idea-board-staging."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "availability_zones" {
  description = "At least two availability zones within region."
  type        = list(string)
}

variable "vpc_cidr" {
  description = "IPv4 VPC range."
  type        = string
  default     = "10.10.0.0/16"
}
