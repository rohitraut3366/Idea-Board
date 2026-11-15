mock_provider "aws" {
  override_during = plan
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/test-role"
    }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address            = "postgres.test.internal"
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test" }]
    }
  }

}

variables {
  name               = "idea-board-test"
  region             = "us-east-1"
  availability_zones = ["us-east-1a", "us-east-1b"]
  kubernetes_version = "1.35"
  admin_role_arn     = "arn:aws:iam::123456789012:role/test-admin"
}

run "configuration" {
  command = plan

  assert {
    condition     = output.cluster_name == var.name && output.database_name == "idea_board" && output.database_port == 5432
    error_message = "Expose the cluster and application database contract."
  }

  assert {
    condition     = output.database_host == "postgres.test.internal" && output.database_credential_secret_id == "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    error_message = "Forward the private database endpoint and managed credential reference."
  }
}
