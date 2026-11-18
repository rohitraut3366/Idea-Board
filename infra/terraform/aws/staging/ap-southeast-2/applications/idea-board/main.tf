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

provider "github" {
  owner = "rohitraut3366"
}

module "psql" {
  source                 = "../../../../../modules/aws/psql"
  name                   = var.name
  vpc_id                 = var.vpc_id
  private_subnet_ids     = var.private_subnet_ids
  node_security_group_id = var.node_security_group_id
  instance_class         = var.database_instance_class
  storage_gb             = var.database_storage_gb
  multi_az               = var.database_multi_az
  deletion_protection    = var.deletion_protection
  skip_final_snapshot    = var.database_skip_final_snapshot
  backup_retention_days  = var.database_backup_retention_days
}

module "backend_values" {
  source       = "../../../../../modules/github/helm-values"
  chart_path   = "charts/idea-board-backend"
  cloud        = "aws"
  cluster_name = var.cluster_name
  values = {
    externalSecret = {
      enabled          = true
      fullnameOverride = "backend-database"
      secretName       = "idea-board-database"
      provider         = { aws = { service = "SecretsManager", region = var.region } }
      dataFrom         = [{ extract = { key = module.psql.credential_secret_id } }]
    }
  }
}
