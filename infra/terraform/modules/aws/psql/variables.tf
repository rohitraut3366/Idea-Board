variable "name" {
  description = "Prefix for PostgreSQL resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC containing the cluster and database."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private database subnets in at least two availability zones."
  type        = list(string)
}

variable "node_security_group_id" {
  description = "Worker security group allowed to connect to PostgreSQL."
  type        = string
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "storage_gb" {
  description = "Initial database storage in GiB."
  type        = number
  default     = 20
}

variable "multi_az" {
  description = "Maintain an RDS standby in another availability zone."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Block accidental database deletion."
  type        = bool
  default     = true
}

variable "skip_final_snapshot" {
  description = "Skip the final database snapshot for a disposable deployment."
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  description = "Number of days to retain automated database backups."
  type        = number
  default     = 7
}
