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
  name       = include.root.locals.environment.inputs.name
  region     = include.root.locals.region.name
  project_id = include.root.locals.environment.inputs.project_id

  network_id   = dependency.networking.outputs.network_id
  cluster_name = dependency.cluster.outputs.cluster_name
}
