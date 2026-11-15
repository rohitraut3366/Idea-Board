provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "required" {
  for_each           = toset(["cloudresourcemanager.googleapis.com", "compute.googleapis.com", "servicenetworking.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "network" {
  source        = "../../../../modules/gcp/network"
  name          = var.name
  region        = var.region
  subnet_cidr   = var.subnet_cidr
  pods_cidr     = var.pods_cidr
  services_cidr = var.services_cidr
  depends_on    = [google_project_service.required]
}
