resource "google_service_account" "nodes" {
  account_id   = "${var.name}-nodes"
  display_name = "${var.name} GKE workers"
}

resource "google_project_iam_member" "nodes" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.nodes.email}"
}
