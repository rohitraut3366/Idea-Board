include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

inputs = {
  name       = include.root.locals.environment.inputs.name
  region     = include.root.locals.region.name
  project_id = include.root.locals.environment.inputs.project_id

  subnet_cidr   = "10.20.0.0/20"
  pods_cidr     = "10.24.0.0/14"
  services_cidr = "10.28.0.0/20"
}
