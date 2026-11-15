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

data "terraform_remote_state" "networking" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "${var.state_prefix}/networking.tfstate"
    region = var.state_region
  }
}

data "terraform_remote_state" "cluster" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "${var.state_prefix}/cluster.tfstate"
    region = var.state_region
  }
}

module "psql" {
  source                 = "../../../../../modules/aws/psql"
  name                   = var.name
  vpc_id                 = data.terraform_remote_state.networking.outputs.vpc_id
  private_subnet_ids     = data.terraform_remote_state.networking.outputs.private_subnet_ids
  node_security_group_id = data.terraform_remote_state.cluster.outputs.node_security_group_id
  instance_class         = var.database_instance_class
  storage_gb             = var.database_storage_gb
  multi_az               = var.database_multi_az
  deletion_protection    = var.deletion_protection
  skip_final_snapshot    = var.database_skip_final_snapshot
  backup_retention_days  = var.database_backup_retention_days
}
