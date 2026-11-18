include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

inputs = {
  name   = include.root.locals.environment.inputs.name
  region = include.root.locals.region.name

  availability_zones = include.root.locals.region.availability_zones
  vpc_cidr           = "10.10.0.0/16"
}
