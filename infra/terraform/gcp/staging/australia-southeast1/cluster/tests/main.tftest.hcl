mock_provider "google" {
  override_during = plan

  mock_resource "google_service_account" {
    defaults = { email = "idea-board-nodes@test-project.iam.gserviceaccount.com" }
  }
}

override_data {
  target = data.terraform_remote_state.networking
  values = { outputs = { network_id = "projects/test-project/global/networks/test", subnetwork_id = "projects/test-project/regions/us-central1/subnetworks/test", pods_range_name = "pods", services_range_name = "services" } }
}

variables {
  state_prefix       = "infra/terraform/gcp/staging/australia-southeast1"
  name               = "idea-board-test"
  region             = "us-central1"
  project_id         = "test-project"
  state_bucket       = "test-state-bucket"
  kubernetes_version = "1.36.4-gke.1469000"
  node_zones         = ["us-central1-a", "us-central1-b"]
}

run "configuration" {
  command = plan
  assert {
    condition     = output.cluster_name == var.name
    error_message = "Publish the provisioned cluster name."
  }
  assert {
    condition     = data.terraform_remote_state.networking.config.bucket == var.state_bucket && data.terraform_remote_state.networking.config.prefix == "infra/terraform/gcp/staging/australia-southeast1/networking"
    error_message = "Read the networking state from the same environment."
  }
  assert {
    condition     = alltrue([for api in google_project_service.required : !api.disable_on_destroy])
    error_message = "Keep project APIs enabled during teardown."
  }
}
