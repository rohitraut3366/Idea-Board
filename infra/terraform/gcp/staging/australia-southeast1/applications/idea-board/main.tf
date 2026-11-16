provider "google" {
  project = var.project_id
  region  = var.region
}

provider "github" {
  owner = "rohitraut3366"
}

data "terraform_remote_state" "networking" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "${var.state_prefix}/networking.tfstate"
    region = var.state_region
  }
}

data "terraform_remote_state" "cluster" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "${var.state_prefix}/cluster.tfstate"
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
  deletion_protection = var.deletion_protection
  depends_on          = [google_project_service.required]
}


module "backend_values" {
  source       = "../../../../../modules/github/helm-values"
  chart_path   = "charts/idea-board-backend"
  cloud        = "gcp"
  cluster_name = data.terraform_remote_state.cluster.outputs.cluster_name
  values = {
    externalSecret = {
      enabled          = true
      fullnameOverride = "backend-database"
      secretName       = "idea-board-database"
      provider         = { gcpsm = { projectID = var.project_id } }
      dataFrom         = [{ extract = { key = basename(module.psql.credential_secret_id) } }]
    }
  }
}
