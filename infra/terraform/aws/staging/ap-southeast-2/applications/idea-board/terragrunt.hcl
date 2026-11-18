include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
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
  name   = include.root.locals.environment.inputs.name
  region = include.root.locals.region.name

  vpc_id                 = dependency.networking.outputs.vpc_id
  private_subnet_ids     = dependency.networking.outputs.private_subnet_ids
  node_security_group_id = dependency.cluster.outputs.node_security_group_id
  cluster_name           = dependency.cluster.outputs.cluster_name
}
