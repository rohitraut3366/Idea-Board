include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependency "networking" {
  config_path = "../../networking"
}

dependency "cluster" {
  config_path = "../../cluster"
}

dependencies {
  paths = ["../../cluster-core-services"]
}

inputs = {
  vpc_id                 = dependency.networking.outputs.vpc_id
  private_subnet_ids     = dependency.networking.outputs.private_subnet_ids
  node_security_group_id = dependency.cluster.outputs.node_security_group_id
  cluster_name           = dependency.cluster.outputs.cluster_name

  database_backup_retention_days = 0
}
