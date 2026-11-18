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

variables {
  private_subnet_ids = ["subnet-11111111", "subnet-22222222"]
  name               = "idea-board-test"
  region             = "us-east-1"
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
