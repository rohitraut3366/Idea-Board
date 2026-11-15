output "host" {
  description = "Private PostgreSQL address."
  value       = google_sql_database_instance.this.private_ip_address
}

output "port" {
  description = "PostgreSQL port."
  value       = 5432
}

output "database_name" {
  description = "Application database."
  value       = google_sql_database.this.name
}

output "username" {
  description = "Initial database owner; use a scoped runtime user for production."
  value       = google_sql_user.this.name
}

output "credential_secret_id" {
  description = "Secret Manager resource ID containing the database credentials."
  value       = google_secret_manager_secret.database.id
}
