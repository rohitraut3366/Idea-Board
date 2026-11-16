mock_provider "aws" {
  override_during = plan
  mock_resource "aws_eks_cluster" {
    defaults = {
      identity = [{ oidc = [{ issuer = "https://oidc.eks.us-east-1.amazonaws.com/id/test" }] }]
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/test-role"
    }
  }
}

variables {
  name               = "idea-board-test"
  private_subnet_ids = ["subnet-11111111", "subnet-22222222"]
  kubernetes_version = "1.35"
  admin_role_arn     = "arn:aws:iam::123456789012:role/test-admin"
  node_count         = 4
}

run "configuration" {
  command = plan

  assert {
    condition     = aws_iam_openid_connect_provider.this.url == aws_eks_cluster.this.identity[0].oidc[0].issuer && aws_iam_openid_connect_provider.this.client_id_list == toset(["sts.amazonaws.com"])
    error_message = "Register the cluster issuer once for services using IRSA."
  }

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && aws_eks_cluster.this.vpc_config[0].endpoint_public_access && aws_eks_cluster.this.vpc_config[0].public_access_cidrs == toset(["0.0.0.0/0"])
    error_message = "The API must be reachable from any public IPv4 address and from the private network."
  }

  assert {
    condition     = toset(aws_eks_node_group.this.subnet_ids) == toset(var.private_subnet_ids)
    error_message = "Workers must use the supplied private subnets."
  }

  assert {
    condition     = aws_eks_node_group.this.scaling_config[0].desired_size == 4 && aws_eks_node_group.this.scaling_config[0].max_size == 4
    error_message = "The configured total worker count must control capacity."
  }

  assert {
    condition     = aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions && aws_eks_access_entry.admin.principal_arn == var.admin_role_arn && aws_eks_access_policy_association.admin.policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    error_message = "IAM access entries must grant cluster administration to the explicit admin role."
  }
}
