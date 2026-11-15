output "name" {
  description = "Kubernetes cluster name."
  value       = aws_eks_cluster.this.name
}

output "node_security_group_id" {
  description = "EKS security group also attached to managed worker nodes."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}
