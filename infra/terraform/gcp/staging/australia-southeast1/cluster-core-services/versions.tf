terraform {
  required_version = "~> 1.17.0"

  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11.0"
    }
  }
}
