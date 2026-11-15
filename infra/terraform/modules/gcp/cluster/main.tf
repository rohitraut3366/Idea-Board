resource "google_container_cluster" "this" {
  name           = var.name
  location       = var.region
  node_locations = var.node_zones
  network        = var.network_id
  subnetwork     = var.subnetwork_id
  # GKE 1.36.4-gke.1469000+ supports creating the cluster without a default pool.
  initial_node_count  = 0
  min_master_version  = var.kubernetes_version
  deletion_protection = var.deletion_protection
  release_channel {
    channel = "REGULAR"
  }
  addons_config {
    http_load_balancing {
      disabled = false
    }
  }
  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range_name
    services_secondary_range_name = var.services_range_name
  }
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  depends_on = [google_project_iam_member.nodes]
}

resource "google_container_node_pool" "this" {
  name           = "${var.name}-nodes"
  location       = var.region
  cluster        = google_container_cluster.this.name
  node_locations = var.node_zones
  node_count     = var.node_count / length(var.node_zones)
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  node_config {
    machine_type    = var.node_machine_type
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    disk_size_gb    = 30
    disk_type       = "pd-balanced"
    metadata = {
      disable-legacy-endpoints = "true"
    }
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
  lifecycle {
    precondition {
      condition     = var.node_count >= length(var.node_zones) && var.node_count % length(var.node_zones) == 0
      error_message = "node_count must be a positive multiple of the number of node_zones."
    }
  }
}
