resource "helm_release" "this" {
  name            = "aws-load-balancer-controller"
  namespace       = "kube-system"
  repository      = "https://aws.github.io/eks-charts"
  chart           = "aws-load-balancer-controller"
  version         = "3.6.3"
  atomic          = true
  cleanup_on_fail = true
  wait            = true
  timeout         = 600
  values = [yamlencode({
    clusterName                 = var.cluster_name
    region                      = var.region
    vpcId                       = var.vpc_id
    serviceAccount              = { create = true, name = "aws-load-balancer-controller" }
    enableServiceMutatorWebhook = false
  })]
  depends_on = [aws_eks_pod_identity_association.controller]
}
