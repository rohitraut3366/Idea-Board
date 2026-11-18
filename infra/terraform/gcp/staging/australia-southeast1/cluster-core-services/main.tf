provider "google" {
  project = var.project_id
  region  = var.region
}

provider "github" {
  owner = "rohitraut3366"
}

data "google_container_cluster" "this" {
  name     = var.cluster_name
  location = var.region
}

provider "helm" {
  kubernetes = {
    host                   = "https://${data.google_container_cluster.this.endpoint}"
    cluster_ca_certificate = base64decode(data.google_container_cluster.this.master_auth[0].cluster_ca_certificate)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "gke-gcloud-auth-plugin"
      args        = ["--use_application_default_credentials"]
    }
  }
}

module "argocd" {
  source          = "../../../../modules/argocd"
  gitops_revision = var.gitops_revision
  cloud           = "gcp"
  cluster_name    = var.cluster_name
}

module "external_secrets" {
  source       = "../../../../modules/gcp/external-secrets"
  name         = var.name
  cluster_name = var.cluster_name
  project_id   = var.project_id
}

moved {
  from = module.external_secrets_values
  to   = module.external_secrets.module.values_file
}
