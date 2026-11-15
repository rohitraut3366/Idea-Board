mock_provider "aws" {
  override_during = plan
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/controller" }
  }
}

variables {
  name         = "idea-board-staging"
  cluster_name = "idea-board-staging"
  region       = "us-east-1"
  vpc_id       = "vpc-12345678"
}

run "controller_setup" {
  command = plan
  assert {
    condition     = aws_eks_addon.pod_identity.addon_name == "eks-pod-identity-agent" && aws_eks_pod_identity_association.controller.namespace == "kube-system" && aws_eks_pod_identity_association.controller.service_account == "aws-load-balancer-controller"
    error_message = "The controller must use Pod Identity through its own service account."
  }
  assert {
    condition     = jsondecode(aws_iam_role.controller.assume_role_policy).Statement[0].Condition.StringEquals["aws:RequestTag/eks-cluster-name"] == var.cluster_name
    error_message = "The controller role must be scoped to the supplied EKS cluster."
  }
  assert {
    condition     = yamldecode(output.controller_application).spec.source.targetRevision == "3.6.3" && yamldecode(output.controller_application).spec.source.helm.valuesObject.vpcId == var.vpc_id && yamldecode(output.controller_application).spec.source.helm.valuesObject.clusterName == var.cluster_name
    error_message = "Export a pinned controller Application configured for the existing cluster and VPC."
  }
  assert {
    condition     = yamldecode(output.controller_application).spec.destination.namespace == "kube-system" && contains(yamldecode(output.controller_application).spec.syncPolicy.syncOptions, "RespectIgnoreDifferences=true")
    error_message = "Install in kube-system and preserve generated webhook credentials on reconciliation."
  }
}
