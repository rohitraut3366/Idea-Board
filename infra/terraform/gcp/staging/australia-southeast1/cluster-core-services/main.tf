provider "google" {
  project = var.project_id
  region  = var.region
}

data "terraform_remote_state" "cluster" {
  backend = "gcs"
  config = {
    bucket = var.state_bucket
    prefix = "${var.state_prefix}/cluster"
  }
}

data "google_container_cluster" "this" {
  name     = data.terraform_remote_state.cluster.outputs.cluster_name
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
  source = "../../../../modules/argocd"
}
