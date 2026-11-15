output "host" {
  description = "Private PostgreSQL hostname."
  value       = aws_db_instance.this.address
}

output "port" {
  description = "PostgreSQL port."
  value       = aws_db_instance.this.port
}

output "database_name" {
  description = "Application database."
  value       = aws_db_instance.this.db_name
}

output "username" {
  description = "Initial database owner; use a scoped runtime user for production."
  value       = aws_db_instance.this.username
}

output "credential_secret_id" {
  description = "AWS Secrets Manager ARN containing the managed database password."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
