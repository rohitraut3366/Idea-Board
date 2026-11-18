include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependency "cluster" {
  config_path = "../cluster"
}

dependency "networking" {
  config_path = "../networking"
}

inputs = {
  cluster_name = dependency.cluster.outputs.cluster_name
  vpc_id       = dependency.networking.outputs.vpc_id
}
