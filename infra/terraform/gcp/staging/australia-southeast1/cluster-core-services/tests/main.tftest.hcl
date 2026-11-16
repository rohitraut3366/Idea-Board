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
override_data {
  target = data.terraform_remote_state.cluster
  values = { outputs = { cluster_name = "idea-board-test", node_security_group_id = "sg-11111111" } }
}

variables {
  state_region = "ap-southeast-2"
  state_prefix = "infra/terraform/gcp/staging/australia-southeast1"
  name         = "idea-board-test"
  region       = "us-central1"
  project_id   = "test-project"
  state_bucket = "test-state-bucket"
}

run "configuration" {
  command = plan
  assert {
    condition     = module.external_secrets.helm_values.serviceAccount.annotations["iam.gke.io/gcp-service-account"] == "idea-board-test-eso@test-project.iam.gserviceaccount.com"
    error_message = "Generate the operator annotation from its provisioned cloud identity."
  }
  assert {
    condition     = module.external_secrets.values_file_path == "charts/external-secrets/values/gcp/idea-board-test/values-terraform.yaml"
    error_message = "Publish GCP values for the cluster read from state."
  }
  assert {
    condition     = output.argocd_namespace == "argocd"
    error_message = "Install the shared Argo CD module."
  }
  assert {
    condition     = data.terraform_remote_state.cluster.config.bucket == var.state_bucket && data.terraform_remote_state.cluster.backend == "s3" && data.terraform_remote_state.cluster.config.region == var.state_region && data.terraform_remote_state.cluster.config.key == "infra/terraform/gcp/staging/australia-southeast1/cluster.tfstate"
    error_message = "Read the cluster state from the same environment."
  }
}
