provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "idea-board", Stack = var.name, ManagedBy = "terraform" }
  }
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

data "aws_eks_cluster" "this" {
  name = data.terraform_remote_state.cluster.outputs.cluster_name
}

provider "helm" {
  kubernetes = {
    host                   = data.aws_eks_cluster.this.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", data.aws_eks_cluster.this.name, "--region", var.region]
    }
  }
}

module "argocd" {
  source                  = "../../../../modules/argocd"
  gitops_revision         = var.gitops_revision
  external_secrets_values = var.external_secrets_values
}

module "load_balancer_controller" {
  source       = "../../../../modules/aws/load-balancer-controller"
  name         = var.name
  region       = var.region
  cluster_name = data.terraform_remote_state.cluster.outputs.cluster_name
  vpc_id       = data.terraform_remote_state.networking.outputs.vpc_id
}
