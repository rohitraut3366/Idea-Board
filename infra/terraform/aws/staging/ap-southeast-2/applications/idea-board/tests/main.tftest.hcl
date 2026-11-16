mock_provider "github" {}

mock_provider "aws" {
  override_during = plan

  mock_resource "aws_db_instance" {
    defaults = {
      address = "postgres.test.internal"
    }
  }

  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test" }
  }
}

mock_provider "random" {}

override_data {
  target = data.terraform_remote_state.networking
  values = { outputs = { vpc_id = "vpc-11111111", private_subnet_ids = ["subnet-11111111", "subnet-22222222"] } }
}

override_data {
  target = data.terraform_remote_state.cluster
  values = { outputs = { cluster_name = "idea-board-test", node_security_group_id = "sg-11111111" } }
}

variables {
  state_prefix = "infra/terraform/aws/staging/ap-southeast-2"
  state_region = "ap-southeast-2"
  name         = "idea-board-test"
  region       = "us-east-1"
  state_bucket = "test-state-bucket"
}

run "configuration" {
  command = plan
  assert {
    condition     = output.database_host == "postgres.test.internal" && output.database_port == 5432 && output.database_name == "idea_board" && output.database_credential_secret_id == "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    error_message = "The application project must expose its private database and credential secret."
  }
  assert {
    condition     = data.terraform_remote_state.networking.config.bucket == var.state_bucket && data.terraform_remote_state.networking.config.key == "infra/terraform/aws/staging/ap-southeast-2/networking.tfstate"
    error_message = "Read the networking state from the same environment."
  }
  assert {
    condition     = data.terraform_remote_state.cluster.config.bucket == var.state_bucket && data.terraform_remote_state.cluster.config.key == "infra/terraform/aws/staging/ap-southeast-2/cluster.tfstate"
    error_message = "Read the cluster state from the same environment."
  }
}

run "backend_secret_values" {
  command = plan
  assert {
    condition     = module.backend_values.file_path == "charts/idea-board-backend/values/aws/idea-board-test/values-terraform.yaml"
    error_message = "Publish the backend's generated values under its cloud and cluster."
  }
  assert {
    condition     = module.backend_values.file_content != "" && yamldecode(module.backend_values.file_content).externalSecret.secretName == "idea-board-database" && yamldecode(module.backend_values.file_content).externalSecret.enabled
    error_message = "Configure External Secrets to create the backend database Secret."
  }
  assert {
    condition     = yamldecode(module.backend_values.file_content).externalSecret.dataFrom[0].extract.key == output.database_credential_secret_id && yamldecode(module.backend_values.file_content).externalSecret.provider.aws.region == var.region
    error_message = "Pass the provider and remote secret reference to External Secrets."
  }
  assert {
    condition     = !can(yamldecode(module.backend_values.file_content).externalSecret.password) && !can(yamldecode(module.backend_values.file_content).externalSecret.DATABASE_URL)
    error_message = "Database passwords and connection URLs must not be published to GitHub."
  }

}
