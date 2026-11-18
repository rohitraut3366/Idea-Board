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

variables {
  vpc_id                 = "vpc-11111111"
  private_subnet_ids     = ["subnet-11111111", "subnet-22222222"]
  node_security_group_id = "sg-11111111"
  cluster_name           = "idea-board-test"
  name                   = "idea-board-test"
  region                 = "us-east-1"
}

run "configuration" {
  command = plan
  assert {
    condition     = output.database_host == "postgres.test.internal" && output.database_port == 5432 && output.database_name == "idea_board" && output.database_credential_secret_id == "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    error_message = "The application project must expose its private database and credential secret."
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
