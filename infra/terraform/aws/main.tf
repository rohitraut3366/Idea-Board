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
  source             = "../modules/aws/network"
  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

module "cluster" {
  source             = "../modules/aws/cluster"
  name               = var.name
  private_subnet_ids = module.network.private_subnet_ids
  kubernetes_version = var.kubernetes_version
  admin_role_arn     = var.admin_role_arn
  node_instance_type = var.node_instance_type
  node_count         = var.node_count
}

module "psql" {
  source                 = "../modules/aws/psql"
  name                   = var.name
  vpc_id                 = module.network.vpc_id
  private_subnet_ids     = module.network.private_subnet_ids
  node_security_group_id = module.cluster.node_security_group_id
  instance_class         = var.database_instance_class
  storage_gb             = var.database_storage_gb
  multi_az               = var.database_multi_az
  deletion_protection    = var.deletion_protection
  skip_final_snapshot    = var.database_skip_final_snapshot
  backup_retention_days  = var.database_backup_retention_days
}
