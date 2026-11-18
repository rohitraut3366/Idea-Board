include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependency "networking" {
  config_path = "../networking"
}

inputs = {
  private_subnet_ids = dependency.networking.outputs.private_subnet_ids

  kubernetes_version = "1.35"
  node_instance_type = "c7i-flex.large"
  node_count         = 2
}
