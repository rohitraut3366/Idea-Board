mock_provider "aws" {
  override_during = plan

  mock_resource "aws_eks_cluster" {
    defaults = {
      identity = [{ oidc = [{ issuer = "https://oidc.eks.us-east-1.amazonaws.com/id/test" }] }]
    }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test-role" }
  }
  mock_data "aws_caller_identity" {
    defaults = { arn = "arn:aws:sts::123456789012:assumed-role/current-admin/session" }
  }
  mock_data "aws_iam_session_context" {
    defaults = { issuer_arn = "arn:aws:iam::123456789012:role/current-admin" }
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
    condition     = output.admin_principal_arn == var.admin_role_arn
    error_message = "Respect an explicitly declared administrator role."
  }
  assert {
    condition     = output.cluster_name == var.name
    error_message = "Publish the provisioned cluster name."
  }
  assert {
    condition     = data.terraform_remote_state.networking.config.bucket == var.state_bucket && data.terraform_remote_state.networking.config.key == "infra/terraform/aws/staging/ap-southeast-2/networking.tfstate"
    error_message = "Read the networking state from the same environment."
  }
}

run "current_login_admin" {
  command = plan
  variables {
    admin_role_arn = null
  }
  assert {
    condition     = data.aws_iam_session_context.current.arn == data.aws_caller_identity.current.arn && output.admin_principal_arn == "arn:aws:iam::123456789012:role/current-admin"
    error_message = "Resolve the active login to its IAM role, not its temporary STS session."
  }
}
