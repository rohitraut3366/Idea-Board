terraform {
  required_version = "~> 1.17.0"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.13.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73.0"
    }
  }
}
