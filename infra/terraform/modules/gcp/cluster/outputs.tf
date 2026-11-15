output "name" {
  description = "Kubernetes cluster name."
  value       = google_container_cluster.this.name
}
