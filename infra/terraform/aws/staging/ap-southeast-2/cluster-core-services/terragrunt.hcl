include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "cluster" {
  config_path = "../cluster"
}

dependency "networking" {
  config_path = "../networking"
}

inputs = {
  name   = include.root.locals.environment.inputs.name
  region = include.root.locals.region.name

  cluster_name = dependency.cluster.outputs.cluster_name
  vpc_id       = dependency.networking.outputs.vpc_id
}
