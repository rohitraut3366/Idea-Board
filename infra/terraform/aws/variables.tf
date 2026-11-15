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

variable "database_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "database_storage_gb" {
  description = "Initial RDS storage in GiB."
  type        = number
  default     = 20
}

variable "database_multi_az" {
  description = "Enable a standby database in another zone."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Protect the database from accidental deletion."
  type        = bool
  default     = true
}

variable "database_skip_final_snapshot" {
  description = "Skip the final RDS snapshot when removing a disposable deployment."
  type        = bool
  default     = false
}

variable "database_backup_retention_days" {
  description = "RDS automated backup retention in days; Free Plan accounts may require a shorter period."
  type        = number
  default     = 7
}
