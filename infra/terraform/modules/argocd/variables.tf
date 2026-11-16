variable "repository_url" {
  description = "Git repository containing the shared Applications chart."
  type        = string
  default     = "https://github.com/rohitraut3366/Idea-Board.git"
}

variable "gitops_revision" {
  description = "Git branch, tag, or commit containing the shared Applications chart."
  type        = string
  default     = "master"
}

variable "cloud" {
  description = "Cloud name used to select service values files."
  type        = string
}

variable "cluster_name" {
  description = "Cluster name used to select service values files."
  type        = string
}
