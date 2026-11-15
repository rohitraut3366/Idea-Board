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
