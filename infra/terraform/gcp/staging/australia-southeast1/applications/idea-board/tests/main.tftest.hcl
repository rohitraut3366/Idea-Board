mock_provider "github" {}

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

override_data {
  target = data.terraform_remote_state.cluster
  values = { outputs = { cluster_name = "idea-board-test" } }
}

run "backend_secret_values" {
  command = plan
  assert {
    condition     = module.backend_values.file_path == "charts/idea-board-backend/values/gcp/idea-board-test/values-terraform.yaml"
    error_message = "Publish the backend's generated values under its cloud and cluster."
  }
  assert {
    condition     = module.backend_values.file_content != "" && yamldecode(module.backend_values.file_content).externalSecret.secretName == "idea-board-database" && yamldecode(module.backend_values.file_content).externalSecret.enabled
    error_message = "Configure External Secrets to create the backend database Secret."
  }
  assert {
    condition     = yamldecode(module.backend_values.file_content).externalSecret.dataFrom[0].extract.key == basename(output.database_credential_secret_id) && yamldecode(module.backend_values.file_content).externalSecret.provider.gcpsm.projectID == var.project_id
    error_message = "Pass the provider and remote secret reference to External Secrets."
  }
  assert {
    condition     = !can(yamldecode(module.backend_values.file_content).externalSecret.password) && !can(yamldecode(module.backend_values.file_content).externalSecret.DATABASE_URL)
    error_message = "Database passwords and connection URLs must not be published to GitHub."
  }

}
