mock_provider "google" {
  override_during = plan

  mock_resource "google_service_account" {
    defaults = { email = "idea-board-nodes@test-project.iam.gserviceaccount.com" }
  }
}

variables {
  network_id          = "projects/test-project/global/networks/test"
  subnetwork_id       = "projects/test-project/regions/us-central1/subnetworks/test"
  pods_range_name     = "pods"
  services_range_name = "services"
  name                = "idea-board-test"
  region              = "us-central1"
  project_id          = "test-project"
  kubernetes_version  = "1.36.4-gke.1469000"
  node_zones          = ["us-central1-a", "us-central1-b"]
}

run "configuration" {
  command = plan
  assert {
    condition     = output.cluster_name == var.name
    error_message = "Publish the provisioned cluster name."
  }
  assert {
    condition     = alltrue([for api in google_project_service.required : !api.disable_on_destroy])
    error_message = "Keep project APIs enabled during teardown."
  }
}
