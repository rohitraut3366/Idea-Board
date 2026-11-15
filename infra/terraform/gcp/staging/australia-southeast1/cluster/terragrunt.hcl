include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  region = read_terragrunt_config(find_in_parent_folders("region.hcl")).locals
}

dependencies {
  paths = ["../networking"]
}

inputs = {
  kubernetes_version = "1.36.4-gke.1469000"
  node_zones         = local.region.node_zones
  node_machine_type  = "e2-standard-2"
  node_count         = 2
}
