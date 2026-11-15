mock_provider "aws" {
  override_during = plan
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test-controller" }
  }
}

mock_provider "helm" {}
variables {
  name         = "idea-board-test"
  region       = "us-east-1"
  cluster_name = "idea-board-test"
  vpc_id       = "vpc-11111111"
}

run "configuration" {
  command = plan
  assert {
    condition     = aws_eks_pod_identity_association.controller.cluster_name == var.cluster_name && aws_eks_pod_identity_association.controller.service_account == "aws-load-balancer-controller" && aws_eks_pod_identity_association.controller.namespace == "kube-system"
    error_message = "Bind controller credentials to this cluster and service account."
  }
  assert {
    condition     = yamldecode(helm_release.this.values[0]).vpcId == var.vpc_id && helm_release.this.wait
    error_message = "Install the controller against the supplied VPC and wait for readiness."
  }
}
