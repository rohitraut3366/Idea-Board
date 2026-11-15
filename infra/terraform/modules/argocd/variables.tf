variable "repository_url" {
  description = "Git repository containing the cluster service Applications."
  type        = string
  default     = "https://github.com/rohitraut3366/Idea-Board.git"
}

variable "gitops_revision" {
  description = "Git branch, tag, or commit containing the cluster service Applications."
  type        = string
  default     = "master"
}

variable "external_secrets_values" {
  description = "Overrides for the upstream External Secrets chart, such as service account annotations."
  type        = any
  default     = {}
}
