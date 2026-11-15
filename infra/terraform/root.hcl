locals {
  state       = read_terragrunt_config(find_in_parent_folders("state.hcl")).locals
  environment = read_terragrunt_config(find_in_parent_folders("environment.hcl")).locals
  region      = read_terragrunt_config(find_in_parent_folders("region.hcl")).locals
  project     = path_relative_to_include()
  parts       = split("/", local.project)
}

terraform_binary              = "terraform"
terragrunt_version_constraint = "~> 1.2.0"

terraform {
  source            = "${dirname(find_in_parent_folders("root.hcl"))}//${local.project}"
  exclude_from_copy = ["**/*.tfvars", "**/*.tfvars.json"]

  extra_arguments "locked_providers" {
    commands  = ["init"]
    arguments = ["-lockfile=readonly"]
  }
}

remote_state {
  backend = "s3"
  config = {
    bucket                = local.state.bucket
    region                = local.state.region
    key                   = "infra/terraform/${local.project}.tfstate"
    encrypt               = true
    use_lockfile          = true
    disable_bucket_update = true
  }
}

inputs = merge(local.environment.inputs, {
  region       = local.region.name
  state_bucket = local.state.bucket
  state_region = local.state.region
  state_prefix = "infra/terraform/${join("/", slice(local.parts, 0, 3))}"
})
