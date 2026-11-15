output "controller_application" {
  description = "Argo CD Application for the pinned controller, including CRDs."
  value = yamlencode({
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata   = { name = "aws-load-balancer-controller", namespace = "argocd" }
    spec = {
      project = "default"
      source = {
        repoURL        = "https://aws.github.io/eks-charts"
        chart          = "aws-load-balancer-controller"
        targetRevision = "3.6.3"
        helm = {
          releaseName = "aws-load-balancer-controller"
          valuesObject = {
            clusterName                 = var.cluster_name
            region                      = var.region
            vpcId                       = var.vpc_id
            serviceAccount              = { create = true, name = "aws-load-balancer-controller" }
            enableServiceMutatorWebhook = false
          }
        }
      }
      destination = { server = "https://kubernetes.default.svc", namespace = "kube-system" }
      syncPolicy = {
        automated   = { prune = true, selfHeal = true }
        syncOptions = ["ServerSideApply=true", "RespectIgnoreDifferences=true"]
      }
      # Helm generates webhook certificates on render. Preserve the installed pair.
      ignoreDifferences = [
        { group = "", kind = "Secret", name = "aws-load-balancer-tls", namespace = "kube-system", jsonPointers = ["/data"] },
        { group = "admissionregistration.k8s.io", kind = "MutatingWebhookConfiguration", name = "aws-load-balancer-webhook", jqPathExpressions = [".webhooks[].clientConfig.caBundle"] },
        { group = "admissionregistration.k8s.io", kind = "ValidatingWebhookConfiguration", name = "aws-load-balancer-webhook", jqPathExpressions = [".webhooks[].clientConfig.caBundle"] },
      ]
    }
  })
}
