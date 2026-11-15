terraform {
  required_version = "~> 1.17.0"
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11.0"
    }
  }
}
