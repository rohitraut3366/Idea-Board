provider "google" {
  project = var.project_id
  region  = var.region
}

data "terraform_remote_state" "networking" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "${var.state_prefix}/networking.tfstate"
    region = var.state_region
  }
}

resource "google_project_service" "required" {
  for_each           = toset(["container.googleapis.com", "iam.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "cluster" {
  source              = "../../../../modules/gcp/cluster"
  name                = var.name
  project_id          = var.project_id
  region              = var.region
  node_zones          = var.node_zones
  network_id          = data.terraform_remote_state.networking.outputs.network_id
  subnetwork_id       = data.terraform_remote_state.networking.outputs.subnetwork_id
  pods_range_name     = data.terraform_remote_state.networking.outputs.pods_range_name
  services_range_name = data.terraform_remote_state.networking.outputs.services_range_name
  master_cidr         = var.master_cidr
  kubernetes_version  = var.kubernetes_version
  node_machine_type   = var.node_machine_type
  node_count          = var.node_count
  deletion_protection = var.deletion_protection
  depends_on          = [google_project_service.required]
}
