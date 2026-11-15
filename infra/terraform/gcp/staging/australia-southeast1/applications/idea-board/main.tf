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
  for_each           = toset(["sqladmin.googleapis.com", "secretmanager.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "psql" {
  source              = "../../../../../modules/gcp/psql"
  name                = var.name
  region              = var.region
  network_id          = data.terraform_remote_state.networking.outputs.network_id
  tier                = var.database_tier
  storage_gb          = var.database_storage_gb
  regional            = var.database_regional
  password            = var.database_password
  deletion_protection = var.deletion_protection
  depends_on          = [google_project_service.required]
}
