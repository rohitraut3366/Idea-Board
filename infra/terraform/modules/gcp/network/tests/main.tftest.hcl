mock_provider "google" {
  override_during = plan
  mock_resource "google_compute_network" {
    defaults = { id = "projects/test-project/global/networks/test" }
  }
  mock_resource "google_compute_subnetwork" {
    defaults = { id = "projects/test-project/regions/us-central1/subnetworks/test" }
  }

}

variables {
  name          = "idea-board-test"
  region        = "us-central1"
  subnet_cidr   = "10.20.0.0/20"
  pods_cidr     = "10.24.0.0/14"
  services_cidr = "10.28.0.0/20"
}

run "configuration" {
  command = plan

  assert {
    condition     = !google_compute_network.this.auto_create_subnetworks && google_compute_subnetwork.this.private_ip_google_access
    error_message = "Use an explicit subnet with private Google API access."
  }

  assert {
    condition     = toset([for range in google_compute_subnetwork.this.secondary_ip_range : range.ip_cidr_range]) == toset([var.pods_cidr, var.services_cidr])
    error_message = "Pods and services must have their own configured ranges."
  }

  assert {
    condition     = google_compute_router_nat.this.source_subnetwork_ip_ranges_to_nat == "LIST_OF_SUBNETWORKS" && one(google_compute_router_nat.this.subnetwork).name == google_compute_subnetwork.this.id
    error_message = "NAT must serve the cluster subnet."
  }

  assert {
    condition     = google_compute_global_address.database.purpose == "VPC_PEERING" && google_compute_global_address.database.address_type == "INTERNAL" && google_service_networking_connection.database.network == google_compute_network.this.id
    error_message = "Cloud SQL must use a private service connection to this VPC."
  }
}
