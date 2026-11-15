mock_provider "google" {
  override_during = plan
  mock_resource "google_service_account" {
    defaults = {
      email = "idea-board-nodes@test-project.iam.gserviceaccount.com"
    }
  }
  mock_resource "google_compute_network" {
    defaults = { id = "projects/test-project/global/networks/test" }
  }
  mock_resource "google_compute_subnetwork" {
    defaults = { id = "projects/test-project/regions/us-central1/subnetworks/test" }
  }
  mock_resource "google_sql_database_instance" {
    defaults = { private_ip_address = "10.30.0.2" }
  }
  mock_resource "google_secret_manager_secret" {
    defaults = { id = "projects/test-project/secrets/idea-board-test-postgres" }
  }

}

variables {
  name               = "idea-board-test"
  project_id         = "test-project"
  region             = "us-central1"
  node_zones         = ["us-central1-a", "us-central1-b"]
  kubernetes_version = "1.36.4-gke.1469000"
  database_password  = "mock-test-password-only"
}

run "configuration" {
  command = plan

  assert {
    condition     = output.cluster_name == var.name && output.database_name == "idea_board" && output.database_port == 5432
    error_message = "Expose the same application database contract as AWS."
  }

  assert {
    condition     = output.database_host == "10.30.0.2" && output.database_credential_secret_id == "projects/test-project/secrets/idea-board-test-postgres"
    error_message = "Forward the private database endpoint and managed credential reference."
  }

  assert {
    condition     = alltrue([for api in google_project_service.required : !api.disable_on_destroy])
    error_message = "Destroying the stack must not disable APIs used by the project."
  }
}
