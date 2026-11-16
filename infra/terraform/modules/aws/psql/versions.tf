terraform {
  required_version = "~> 1.17.0"
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73.0"
    }
  }
}
