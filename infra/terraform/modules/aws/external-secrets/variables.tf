variable "name" {
  description = "Stack name used for the External Secrets IAM role."
  type        = string
}

variable "oidc_issuer" {
  description = "OIDC issuer URL of the EKS cluster."
  type        = string
}

variable "cluster_name" {
  description = "Cluster receiving the generated Helm values."
  type        = string
}
