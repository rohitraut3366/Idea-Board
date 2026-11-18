include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "networking" {
  config_path = "../networking"
}

inputs = {
  name   = include.root.locals.environment.inputs.name
  region = include.root.locals.region.name

  private_subnet_ids = dependency.networking.outputs.private_subnet_ids

  kubernetes_version = "1.35"
}
