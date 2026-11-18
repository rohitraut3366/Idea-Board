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

variables {
  network_id   = "projects/test-project/global/networks/test"
  cluster_name = "idea-board-test"
  name         = "idea-board-test"
  region       = "us-central1"
  project_id   = "test-project"
}

run "configuration" {
  command = plan
  assert {
    condition     = output.database_host == "10.30.0.2" && output.database_port == 5432 && output.database_name == "idea_board" && output.database_credential_secret_id == "projects/test-project/secrets/idea-board-test-postgres"
    error_message = "The application project must expose its private database and credential secret."
  }
  assert {
    condition     = alltrue([for api in google_project_service.required : !api.disable_on_destroy])
    error_message = "Keep project APIs enabled during teardown."
  }
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
