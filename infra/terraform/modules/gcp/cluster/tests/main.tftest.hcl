mock_provider "google" {
  override_during = plan
  mock_resource "google_service_account" {
    defaults = {
      email = "idea-board-nodes@test-project.iam.gserviceaccount.com"
    }
  }
}

variables {
  name                = "idea-board-test"
  project_id          = "test-project"
  region              = "us-central1"
  node_zones          = ["us-central1-a", "us-central1-b"]
  network_id          = "projects/test-project/global/networks/test"
  subnetwork_id       = "projects/test-project/regions/us-central1/subnetworks/test"
  pods_range_name     = "pods"
  services_range_name = "services"
  master_cidr         = "172.16.0.0/28"
  kubernetes_version  = "1.36.4-gke.1469000"
  node_count          = 4
}

run "configuration" {
  command = plan

  assert {
    condition     = !google_container_cluster.this.addons_config[0].http_load_balancing[0].disabled
    error_message = "Enable the GKE Ingress controller."
  }

  assert {
    condition     = google_container_cluster.this.private_cluster_config[0].enable_private_nodes
    error_message = "Worker nodes must have private addresses."
  }

  assert {
    condition     = !google_container_cluster.this.private_cluster_config[0].enable_private_endpoint && length(google_container_cluster.this.master_authorized_networks_config) == 0
    error_message = "The public Kubernetes API must not require a caller IP allowlist."
  }

  assert {
    condition     = google_container_cluster.this.initial_node_count == 0 && google_container_node_pool.this.node_count == 2 && length(google_container_node_pool.this.node_locations) == 2
    error_message = "Four total workers across two zones must create two workers per zone and no default pool."
  }

  assert {
    condition     = google_container_node_pool.this.node_config[0].service_account == google_service_account.nodes.email && google_project_iam_member.nodes.role == "roles/container.defaultNodeServiceAccount"
    error_message = "Use a dedicated node identity with the GKE node role."
  }

  assert {
    condition     = google_container_node_pool.this.node_config[0].workload_metadata_config[0].mode == "GKE_METADATA"
    error_message = "Pods must use Workload Identity metadata."
  }
}

run "reject_uneven_worker_count" {
  command = plan
  variables {
    node_count = 3
  }
  expect_failures = [google_container_node_pool.this]
}
