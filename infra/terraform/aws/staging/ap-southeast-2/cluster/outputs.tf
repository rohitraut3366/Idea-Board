output "cluster_name" {
  value = module.cluster.name
}

output "admin_principal_arn" {
  description = "IAM principal granted Kubernetes administrator access."
  value       = coalesce(var.admin_role_arn, data.aws_iam_session_context.current.issuer_arn)
}

output "node_security_group_id" {
  value = module.cluster.node_security_group_id
}
