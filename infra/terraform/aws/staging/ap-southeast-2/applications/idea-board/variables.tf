variable "name" {
  description = "Stack name, including environment, for example idea-board-staging."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
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
  description = "RDS automated backup retention in days; 0 disables automated backups."
  type        = number
  default     = 0
}

variable "vpc_id" {
  description = "VPC ID supplied by the networking Terragrunt dependency."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs supplied by the networking Terragrunt dependency."
  type        = list(string)
}

variable "node_security_group_id" {
  description = "Node security group ID supplied by the cluster Terragrunt dependency."
  type        = string
}

variable "cluster_name" {
  description = "Cluster name supplied by the cluster Terragrunt dependency."
  type        = string
}
