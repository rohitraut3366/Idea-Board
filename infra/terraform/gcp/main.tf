provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "required" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "network" {
  source        = "../modules/gcp/network"
  name          = var.name
  region        = var.region
  subnet_cidr   = var.subnet_cidr
  pods_cidr     = var.pods_cidr
  services_cidr = var.services_cidr
  depends_on    = [google_project_service.required]
}

module "cluster" {
  source              = "../modules/gcp/cluster"
  name                = var.name
  project_id          = var.project_id
  region              = var.region
  node_zones          = var.node_zones
  network_id          = module.network.network_id
  subnetwork_id       = module.network.subnetwork_id
  pods_range_name     = module.network.pods_range_name
  services_range_name = module.network.services_range_name
  master_cidr         = var.master_cidr
  kubernetes_version  = var.kubernetes_version
  node_machine_type   = var.node_machine_type
  node_count          = var.node_count
  deletion_protection = var.deletion_protection
  depends_on          = [google_project_service.required]
}

module "psql" {
  source              = "../modules/gcp/psql"
  name                = var.name
  region              = var.region
  network_id          = module.network.network_id
  tier                = var.database_tier
  storage_gb          = var.database_storage_gb
  regional            = var.database_regional
  password            = var.database_password
  deletion_protection = var.deletion_protection
  depends_on          = [google_project_service.required]
}
