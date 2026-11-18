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
  network_id   = dependency.networking.outputs.network_id
  cluster_name = dependency.cluster.outputs.cluster_name
}
