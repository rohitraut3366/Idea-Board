mock_provider "aws" {
  override_during = plan

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test-role" }
  }
}

override_data {
  target = data.terraform_remote_state.networking
  values = { outputs = { vpc_id = "vpc-11111111", private_subnet_ids = ["subnet-11111111", "subnet-22222222"] } }
}

variables {
  state_prefix       = "infra/terraform/aws/staging/ap-southeast-2"
  state_region       = "ap-southeast-2"
  name               = "idea-board-test"
  region             = "us-east-1"
  state_bucket       = "test-state-bucket"
  kubernetes_version = "1.35"
  admin_role_arn     = "arn:aws:iam::123456789012:role/test-admin"
}

run "configuration" {
  command = plan
  assert {
    condition     = output.cluster_name == var.name
    error_message = "Publish the provisioned cluster name."
  }
  assert {
    condition     = data.terraform_remote_state.networking.config.bucket == var.state_bucket && data.terraform_remote_state.networking.config.key == "infra/terraform/aws/staging/ap-southeast-2/networking.tfstate"
    error_message = "Read the networking state from the same environment."
  }
}
