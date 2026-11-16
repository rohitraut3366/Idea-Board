mock_provider "aws" {
  override_during = plan
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/idea-board-test-external-secrets" }
  }
}
mock_provider "github" {}

variables {
  name         = "idea-board-test"
  cluster_name = "idea-board-test"
  oidc_issuer  = "https://oidc.eks.us-east-1.amazonaws.com/id/test"
}

run "operator_irsa" {
  command = plan
  assert {
    condition = (
      jsondecode(aws_iam_role_policy.this.policy).Statement[0].Resource == "arn:aws:secretsmanager:*:123456789012:secret:*" &&
      toset(jsondecode(aws_iam_role_policy.this.policy).Statement[0].Action) == toset(["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy", "secretsmanager:ListSecretVersionIds"]) &&
      toset(jsondecode(aws_iam_role_policy.this.policy).Statement[1].Action) == toset(["secretsmanager:ListSecrets"])
    )
    error_message = "Read all Secrets Manager secrets in the account, without secret-write permissions."
  }
  assert {
    condition     = output.helm_values.serviceAccount.name == "external-secrets" && output.helm_values.serviceAccount.annotations["eks.amazonaws.com/role-arn"] == module.irsa.iam_role_arn && output.values_file_path == "charts/external-secrets/values/aws/idea-board-test/values-terraform.yaml"
    error_message = "Publish the created role annotation to the correct cluster's Helm values."
  }
}
