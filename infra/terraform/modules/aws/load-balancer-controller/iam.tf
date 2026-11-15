resource "aws_eks_addon" "pod_identity" {
  cluster_name = var.cluster_name
  addon_name   = "eks-pod-identity-agent"
}

resource "aws_iam_role" "controller" {
  name = "${var.name}-load-balancer-controller"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
      Condition = {
        StringEquals = {
          "aws:RequestTag/eks-cluster-name"           = var.cluster_name
          "aws:RequestTag/kubernetes-namespace"       = "kube-system"
          "aws:RequestTag/kubernetes-service-account" = "aws-load-balancer-controller"
        }
      }
    }]
  })
}

# Official controller v3.6.3 IAM policy; upgrade with the pinned chart.
resource "aws_iam_role_policy" "controller" {
  name   = "load-balancer-controller"
  role   = aws_iam_role.controller.id
  policy = file("${path.module}/controller-iam-policy.json")
}

resource "aws_eks_pod_identity_association" "controller" {
  cluster_name    = var.cluster_name
  namespace       = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn        = aws_iam_role.controller.arn
  depends_on      = [aws_eks_addon.pod_identity, aws_iam_role_policy.controller]
}
