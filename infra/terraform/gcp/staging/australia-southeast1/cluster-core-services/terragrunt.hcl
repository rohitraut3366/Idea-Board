include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependency "cluster" {
  config_path = "../cluster"
}

inputs = {
  cluster_name = dependency.cluster.outputs.cluster_name
}
