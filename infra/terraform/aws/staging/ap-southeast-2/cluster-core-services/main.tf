provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "idea-board", Stack = var.name, ManagedBy = "terraform" }
  }
}

provider "github" {
  owner = "rohitraut3366"
}

data "aws_eks_cluster" "this" {
  name = var.cluster_name
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
  source          = "../../../../modules/argocd"
  gitops_revision = var.gitops_revision
  cloud           = "aws"
  cluster_name    = var.cluster_name
}

module "external_secrets" {
  source       = "../../../../modules/aws/external-secrets"
  name         = var.name
  cluster_name = var.cluster_name
  oidc_issuer  = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
}

moved {
  from = module.external_secrets_values
  to   = module.external_secrets.module.values_file
}

module "load_balancer_controller" {
  source       = "../../../../modules/aws/load-balancer-controller"
  name         = var.name
  region       = var.region
  cluster_name = var.cluster_name
  vpc_id       = var.vpc_id
}
