mock_provider "aws" {
  override_during = plan

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test-role" }
  }
  mock_data "aws_eks_cluster" {
    defaults = { endpoint = "https://cluster.example.com", certificate_authority = [{ data = "bW9jay1jYQ==" }] }
  }
}

mock_provider "helm" {}
override_data {
  target = data.terraform_remote_state.networking
  values = { outputs = { vpc_id = "vpc-11111111", private_subnet_ids = ["subnet-11111111", "subnet-22222222"] } }
}

override_data {
  target = data.terraform_remote_state.cluster
  values = { outputs = { cluster_name = "idea-board-test", node_security_group_id = "sg-11111111" } }
}

variables {
  state_prefix = "infra/terraform/aws/staging/ap-southeast-2"
  state_region = "ap-southeast-2"
  name         = "idea-board-test"
  region       = "us-east-1"
  state_bucket = "test-state-bucket"
}

run "configuration" {
  command = plan
  assert {
    condition     = output.argocd_namespace == "argocd"
    error_message = "Install the shared Argo CD module."
  }
  assert {
    condition     = data.terraform_remote_state.networking.config.bucket == var.state_bucket && data.terraform_remote_state.networking.config.key == "infra/terraform/aws/staging/ap-southeast-2/networking.tfstate"
    error_message = "Read the networking state from the same environment."
  }
  assert {
    condition     = data.terraform_remote_state.cluster.config.bucket == var.state_bucket && data.terraform_remote_state.cluster.config.key == "infra/terraform/aws/staging/ap-southeast-2/cluster.tfstate"
    error_message = "Read the cluster state from the same environment."
  }
}
