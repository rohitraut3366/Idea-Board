mock_provider "aws" {
  override_during = plan

  mock_resource "aws_db_instance" {
    defaults = {
      address            = "postgres.test.internal"
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test" }]
    }
  }
}

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
