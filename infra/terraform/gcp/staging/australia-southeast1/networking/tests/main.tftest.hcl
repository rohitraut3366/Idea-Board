mock_provider "google" {
  override_during = plan

  mock_resource "google_compute_network" {
    defaults = { id = "projects/test-project/global/networks/test" }
  }
  mock_resource "google_compute_subnetwork" {
    defaults = { id = "projects/test-project/regions/us-central1/subnetworks/test" }
  }
}

variables {
  name       = "idea-board-test"
  region     = "us-central1"
  project_id = "test-project"
}

run "configuration" {
  command = plan
  assert {
    condition     = output.network_id == "projects/test-project/global/networks/test" && output.pods_range_name == "pods"
    error_message = "Publish the private networking contract for dependent projects."
  }
  assert {
    condition     = alltrue([for api in google_project_service.required : !api.disable_on_destroy])
    error_message = "Keep project APIs enabled during teardown."
  }
}
