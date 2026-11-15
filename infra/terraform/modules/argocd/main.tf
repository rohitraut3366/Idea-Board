resource "helm_release" "this" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "10.18.0"
  atomic           = true
  cleanup_on_fail  = true
  wait             = true
  timeout          = 600
  values = [yamlencode({
    server = { service = { type = "ClusterIP" } }
  })]
}

resource "helm_release" "core_services" {
  name      = "cluster-core-services"
  namespace = helm_release.this.namespace
  chart     = "${path.module}/bootstrap"
  atomic    = true
  wait      = true
  values = [yamlencode({
    repositoryURL  = var.repository_url
    targetRevision = var.gitops_revision
    cloud          = var.cloud
    clusterName    = var.cluster_name
  })]
}
