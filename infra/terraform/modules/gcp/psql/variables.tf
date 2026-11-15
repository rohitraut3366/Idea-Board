variable "name" {
  description = "Prefix for PostgreSQL resources."
  type        = string
}

variable "region" {
  description = "Cloud SQL region."
  type        = string
}

variable "network_id" {
  description = "VPC resource ID with Private Service Access configured."
  type        = string
}

variable "tier" {
  description = "Cloud SQL instance tier."
  type        = string
  default     = "db-custom-1-3840"
}

variable "storage_gb" {
  description = "Initial database storage in GiB."
  type        = number
  default     = 20
}

variable "regional" {
  description = "Maintain a Cloud SQL standby in another zone."
  type        = bool
  default     = false
}

variable "password" {
  description = "Initial database owner password, supplied through TF_VAR_database_password."
  type        = string
  sensitive   = true
}

variable "deletion_protection" {
  description = "Block accidental database deletion."
  type        = bool
  default     = true
}
