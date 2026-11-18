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
variables {
  cluster_name = "idea-board-test"
  vpc_id       = "vpc-11111111"
  name         = "idea-board-test"
  region       = "us-east-1"
}

run "configuration" {
  command = plan
  assert {
    condition     = module.external_secrets.helm_values.serviceAccount.annotations["eks.amazonaws.com/role-arn"] == "arn:aws:iam::123456789012:role/test-role"
    error_message = "Generate the operator annotation from its provisioned cloud identity."
  }
  assert {
    condition     = module.external_secrets.values_file_path == "charts/external-secrets/values/aws/idea-board-test/values-terraform.yaml"
    error_message = "Publish AWS values for the cluster supplied by Terragrunt."
  }
  assert {
    condition     = output.argocd_namespace == "argocd"
    error_message = "Install the shared Argo CD module."
  }
}
