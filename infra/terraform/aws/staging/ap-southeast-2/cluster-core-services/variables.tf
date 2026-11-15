variable "name" {
  description = "Stack name, including environment, for example idea-board-staging."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
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
