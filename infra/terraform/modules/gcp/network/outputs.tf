output "network_id" {
  description = "VPC resource ID, ready for private database connections."
  value       = google_compute_network.this.id
  depends_on  = [google_service_networking_connection.database]
}

output "subnetwork_id" {
  description = "Node subnet, ready for outbound image pulls."
  value       = google_compute_subnetwork.this.id
  depends_on  = [google_compute_router_nat.this]
}

output "pods_range_name" {
  description = "Secondary range name for pods."
  value       = "pods"
}

output "services_range_name" {
  description = "Secondary range name for services."
  value       = "services"
}
