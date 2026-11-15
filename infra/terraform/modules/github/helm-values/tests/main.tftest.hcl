mock_provider "github" {}

variables {
  chart_path   = "charts/external-secrets"
  cloud        = "aws"
  cluster_name = "idea-board-staging"
  values = {
    external-secrets = {
      serviceAccount = {
        annotations = { "eks.amazonaws.com/role-arn" = "arn:aws:iam::123456789012:role/external-secrets" }
      }
    }
  }
}

run "aws_values" {
  command = plan
  assert {
    condition     = github_repository_file.this.repository == "Idea-Board" && github_repository_file.this.branch == "master"
    error_message = "Publish values to the application's master branch."
  }
  assert {
    condition     = output.file_path == "charts/external-secrets/values/aws/idea-board-staging/values-terraform.yaml"
    error_message = "Select a separate file for each provider and cluster."
  }
  assert {
    condition     = yamldecode(github_repository_file.this.content).external-secrets.serviceAccount.annotations["eks.amazonaws.com/role-arn"] == "arn:aws:iam::123456789012:role/external-secrets"
    error_message = "Preserve the upstream chart's values structure."
  }
}

run "gcp_values" {
  command = plan
  variables {
    cloud = "gcp"
  }
  assert {
    condition     = output.file_path == "charts/external-secrets/values/gcp/idea-board-staging/values-terraform.yaml"
    error_message = "AWS and GCP must publish different files even when cluster names match."
  }
}
