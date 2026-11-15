output "cluster_name" {
  description = "Kubernetes cluster name."
  value       = module.cluster.name
}

output "vpc_id" {
  description = "VPC used by the post-cluster ingress controller setup."
  value       = module.network.vpc_id
}

output "database_host" {
  description = "Private PostgreSQL address."
  value       = module.psql.host
}

output "database_port" {
  description = "PostgreSQL port."
  value       = module.psql.port
}

output "database_name" {
  description = "Application database."
  value       = module.psql.database_name
}

output "database_username" {
  description = "Initial database owner."
  value       = module.psql.username
}

output "database_credential_secret_id" {
  description = "Cloud secret reference containing database credentials."
  value       = module.psql.credential_secret_id
}
