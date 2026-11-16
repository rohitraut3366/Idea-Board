mock_provider "aws" {
  override_during = plan
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test-role" }
  }
  mock_data "aws_eks_cluster" {
    defaults = {
      endpoint              = "https://cluster.example.com"
      certificate_authority = [{ data = "bW9jay1jYQ==" }]
      identity              = [{ oidc = [{ issuer = "https://oidc.eks.us-east-1.amazonaws.com/id/test" }] }]
    }
  }
}

mock_provider "helm" {}
mock_provider "github" {}
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
    condition     = module.external_secrets.helm_values.serviceAccount.annotations["eks.amazonaws.com/role-arn"] == "arn:aws:iam::123456789012:role/test-role"
    error_message = "Generate the operator annotation from its provisioned cloud identity."
  }
  assert {
    condition     = module.external_secrets.values_file_path == "charts/external-secrets/values/aws/idea-board-test/values-terraform.yaml"
    error_message = "Publish AWS values for the cluster read from state."
  }
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
