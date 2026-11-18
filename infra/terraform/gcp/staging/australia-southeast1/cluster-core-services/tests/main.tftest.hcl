mock_provider "google" {
  override_during = plan

  mock_resource "google_service_account" {
    defaults = {
      name  = "projects/test-project/serviceAccounts/idea-board-test-eso@test-project.iam.gserviceaccount.com"
      email = "idea-board-test-eso@test-project.iam.gserviceaccount.com"
    }
  }
  mock_data "google_container_cluster" {
    defaults = { endpoint = "127.0.0.1", master_auth = [{ cluster_ca_certificate = "bW9jay1jYQ==" }] }
  }
}

mock_provider "helm" {}
mock_provider "github" {}
variables {
  cluster_name = "idea-board-test"
  name         = "idea-board-test"
  region       = "us-central1"
  project_id   = "test-project"
}

run "configuration" {
  command = plan
  assert {
    condition     = module.external_secrets.helm_values.serviceAccount.annotations["iam.gke.io/gcp-service-account"] == "idea-board-test-eso@test-project.iam.gserviceaccount.com"
    error_message = "Generate the operator annotation from its provisioned cloud identity."
  }
  assert {
    condition     = module.external_secrets.values_file_path == "charts/external-secrets/values/gcp/idea-board-test/values-terraform.yaml"
    error_message = "Publish GCP values for the cluster supplied by Terragrunt."
  }
  assert {
    condition     = output.argocd_namespace == "argocd"
    error_message = "Install the shared Argo CD module."
  }
}
