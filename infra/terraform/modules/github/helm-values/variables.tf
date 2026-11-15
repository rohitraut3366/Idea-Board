variable "chart_path" {
  description = "Repository-relative path to the umbrella chart."
  type        = string
}

variable "cloud" {
  description = "Cloud name, for example aws or gcp."
  type        = string
}

variable "cluster_name" {
  description = "Cluster receiving these chart values."
  type        = string
}

variable "values" {
  description = "Non-secret Helm values to publish, such as IAM role annotations."
  type        = any
}
