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

  database_tier       = "db-custom-1-3840"
  database_storage_gb = 20
  database_regional   = false
  deletion_protection = true
}
