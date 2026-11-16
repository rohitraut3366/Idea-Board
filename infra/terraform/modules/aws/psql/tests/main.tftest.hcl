mock_provider "aws" {
  override_during = plan

  mock_resource "aws_db_instance" {
    defaults = { address = "postgres.test.internal" }
  }

  mock_resource "aws_secretsmanager_secret" {
    defaults = {
      id  = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
      arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    }
  }
}

mock_provider "random" {
  override_during = plan

  mock_resource "random_password" {
    defaults = { result = "test+password:?%&" }
  }
}

variables {
  name                   = "idea-board-test"
  vpc_id                 = "vpc-11111111"
  private_subnet_ids     = ["subnet-11111111", "subnet-22222222"]
  node_security_group_id = "sg-11111111"
}

run "configuration" {
  command = plan

  assert {
    condition     = !aws_db_instance.this.publicly_accessible && aws_db_instance.this.storage_encrypted
    error_message = "RDS must be private and encrypted at rest."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.postgres.referenced_security_group_id == var.node_security_group_id && aws_vpc_security_group_ingress_rule.postgres.from_port == 5432 && aws_vpc_security_group_ingress_rule.postgres.to_port == 5432
    error_message = "Only the cluster worker security group may connect on port 5432."
  }

  assert {
    condition     = random_password.database.length == 32 && random_password.database.special && aws_db_instance.this.password == random_password.database.result
    error_message = "Generate the RDS password with the Random provider."
  }

  assert {
    condition     = aws_db_instance.this.backup_retention_period == 0 && aws_db_instance.this.deletion_protection && !aws_db_instance.this.skip_final_snapshot
    error_message = "Disable automated backups by default and protect database deletion."
  }

  assert {
    condition     = toset(aws_db_subnet_group.this.subnet_ids) == toset(var.private_subnet_ids)
    error_message = "RDS must use the supplied private subnets."
  }
}

run "larger_database" {
  command = plan
  variables {
    instance_class = "db.m7g.large"
    storage_gb     = 100
    multi_az       = true
  }
  assert {
    condition     = aws_db_instance.this.multi_az && aws_db_instance.this.allocated_storage == 100 && aws_db_instance.this.instance_class == "db.m7g.large"
    error_message = "Database availability and capacity must follow the configured values."
  }
}

run "disposable_database" {
  command = plan
  variables {
    deletion_protection   = false
    skip_final_snapshot   = true
    backup_retention_days = 1
  }
  assert {
    condition     = !aws_db_instance.this.deletion_protection && aws_db_instance.this.skip_final_snapshot && aws_db_instance.this.final_snapshot_identifier == null && aws_db_instance.this.backup_retention_period == 1
    error_message = "A disposable database must support deletion without retaining a final snapshot."
  }
}

run "connection_secret" {
  command = plan

  assert {
    condition     = jsondecode(aws_secretsmanager_secret_version.database.secret_string).DATABASE_URL == "postgresql+psycopg://idea_board_admin:test%2Bpassword%3A%3F%25%26@postgres.test.internal:5432/idea_board?sslmode=require"
    error_message = "Store the complete TLS connection URL with encoded credentials."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.database.secret_id == aws_secretsmanager_secret.database.id && output.credential_secret_id == aws_secretsmanager_secret.database.arn
    error_message = "Publish the secret reference containing the connection URL."
  }
}
