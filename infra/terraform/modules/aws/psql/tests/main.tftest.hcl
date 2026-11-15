mock_provider "aws" {
  override_during = plan

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
    condition     = aws_db_instance.this.manage_master_user_password && aws_db_instance.this.password == null
    error_message = "AWS must manage the password without a Terraform password input."
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
