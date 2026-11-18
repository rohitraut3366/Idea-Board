include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "networking" {
  config_path = "../networking"
}

inputs = {
  name       = include.root.locals.environment.inputs.name
  region     = include.root.locals.region.name
  project_id = include.root.locals.environment.inputs.project_id

  network_id          = dependency.networking.outputs.network_id
  subnetwork_id       = dependency.networking.outputs.subnetwork_id
  pods_range_name     = dependency.networking.outputs.pods_range_name
  services_range_name = dependency.networking.outputs.services_range_name

  kubernetes_version  = "1.36.4-gke.1469000"
  node_zones          = include.root.locals.region.node_zones
  master_cidr         = "172.16.0.0/28"
  node_machine_type   = "e2-standard-2"
  node_count          = 2
  deletion_protection = true
}
