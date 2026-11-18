provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "idea-board"
      Stack     = var.name
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_iam_session_context" "current" {
  arn = data.aws_caller_identity.current.arn
}

module "cluster" {
  source             = "../../../../modules/aws/cluster"
  name               = var.name
  private_subnet_ids = var.private_subnet_ids
  kubernetes_version = var.kubernetes_version
  admin_role_arn     = coalesce(var.admin_role_arn, data.aws_iam_session_context.current.issuer_arn)
  node_instance_type = var.node_instance_type
  node_count         = var.node_count
}
