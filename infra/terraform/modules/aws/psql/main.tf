resource "random_password" "database" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}:?"
}

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "database" {
  name        = "${var.name}-postgres"
  description = "PostgreSQL access from EKS workers"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = var.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_instance" "this" {
  identifier                 = var.name
  engine                     = "postgres"
  engine_version             = "17"
  instance_class             = var.instance_class
  allocated_storage          = var.storage_gb
  storage_type               = "gp3"
  storage_encrypted          = true
  db_name                    = "idea_board"
  username                   = "idea_board_admin"
  password                   = random_password.database.result
  port                       = 5432
  db_subnet_group_name       = aws_db_subnet_group.this.name
  vpc_security_group_ids     = [aws_security_group.database.id]
  publicly_accessible        = false
  multi_az                   = var.multi_az
  backup_retention_period    = var.backup_retention_days
  auto_minor_version_upgrade = true
  deletion_protection        = var.deletion_protection
  skip_final_snapshot        = var.skip_final_snapshot
  final_snapshot_identifier  = var.skip_final_snapshot ? null : "${var.name}-final"
  copy_tags_to_snapshot      = true
}

resource "aws_secretsmanager_secret" "database" {
  name = "${var.name}-postgres"
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    DATABASE_URL = format(
      "postgresql+psycopg://%s:%s@%s:%s/%s?sslmode=require",
      replace(urlencode(aws_db_instance.this.username), "+", "%20"),
      replace(urlencode(random_password.database.result), "+", "%20"),
      aws_db_instance.this.address,
      aws_db_instance.this.port,
      aws_db_instance.this.db_name,
    )
  })
}
