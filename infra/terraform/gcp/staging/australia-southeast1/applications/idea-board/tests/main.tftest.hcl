mock_provider "google" {
  override_during = plan

  mock_resource "google_sql_database_instance" {
    defaults = { private_ip_address = "10.30.0.2" }
  }
  mock_resource "google_secret_manager_secret" {
    defaults = { id = "projects/test-project/secrets/idea-board-test-postgres" }
  }
}

mock_provider "random" {}

override_data {
  target = data.terraform_remote_state.networking
  values = { outputs = { network_id = "projects/test-project/global/networks/test", subnetwork_id = "projects/test-project/regions/us-central1/subnetworks/test", pods_range_name = "pods", services_range_name = "services" } }
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
    condition     = output.database_host == "10.30.0.2" && output.database_port == 5432 && output.database_name == "idea_board" && output.database_credential_secret_id == "projects/test-project/secrets/idea-board-test-postgres"
    error_message = "The application project must expose its private database and credential secret."
  }
  assert {
    condition     = data.terraform_remote_state.networking.config.bucket == var.state_bucket && data.terraform_remote_state.networking.backend == "s3" && data.terraform_remote_state.networking.config.region == var.state_region && data.terraform_remote_state.networking.config.key == "infra/terraform/gcp/staging/australia-southeast1/networking.tfstate"
    error_message = "Read the networking state from the same environment."
  }
  assert {
    condition     = alltrue([for api in google_project_service.required : !api.disable_on_destroy])
    error_message = "Keep project APIs enabled during teardown."
  }
}
