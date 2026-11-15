include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  region = read_terragrunt_config(find_in_parent_folders("region.hcl")).locals
}

inputs = {
  availability_zones = local.region.availability_zones
}
