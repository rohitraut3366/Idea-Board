provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "idea-board"
      Stack     = var.name
      ManagedBy = "terraform"
    }
  }
}

module "network" {
  source             = "../../../../modules/aws/network"
  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}
