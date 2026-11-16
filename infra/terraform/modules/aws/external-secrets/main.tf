locals {
  helm_values = {
    serviceAccount = {
      name = "external-secrets"
      annotations = {
        "eks.amazonaws.com/role-arn" = module.irsa.iam_role_arn
      }
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

module "irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-assumable-role-with-oidc"
  version = "5.52.1"

  create_role                    = true
  role_name                      = "${var.name}-external-secrets"
  provider_url                   = var.oidc_issuer
  oidc_fully_qualified_subjects  = ["system:serviceaccount:external-secrets:external-secrets"]
  oidc_fully_qualified_audiences = ["sts.amazonaws.com"]
}

resource "aws_iam_role_policy" "this" {
  name = "read-secrets-manager"
  role = module.irsa.iam_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:ListSecretVersionIds",
        ]
        Resource = "arn:${data.aws_partition.current.partition}:secretsmanager:*:${data.aws_caller_identity.current.account_id}:secret:*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:ListSecrets"]
        Resource = "*"
      },
    ]
  })
}

module "values_file" {
  source       = "../../github/helm-values"
  chart_path   = "charts/external-secrets"
  cloud        = "aws"
  cluster_name = var.cluster_name
  values       = { external-secrets = local.helm_values }
  depends_on   = [aws_iam_role_policy.this]
}
