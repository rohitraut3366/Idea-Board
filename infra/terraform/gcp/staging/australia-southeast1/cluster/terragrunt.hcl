include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  region = read_terragrunt_config(find_in_parent_folders("region.hcl")).locals
}

dependency "networking" {
  config_path = "../networking"
}

inputs = {
  network_id          = dependency.networking.outputs.network_id
  subnetwork_id       = dependency.networking.outputs.subnetwork_id
  pods_range_name     = dependency.networking.outputs.pods_range_name
  services_range_name = dependency.networking.outputs.services_range_name

  kubernetes_version = "1.36.4-gke.1469000"
  node_zones         = local.region.node_zones
  node_machine_type  = "e2-standard-2"
  node_count         = 2
}
