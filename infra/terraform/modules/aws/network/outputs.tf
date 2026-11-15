output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "private_subnet_ids" {
  description = "Private subnets for worker nodes and PostgreSQL."
  value       = [for subnet in aws_subnet.private : subnet.id]
  depends_on  = [aws_route.nat, aws_route.internet, aws_route_table_association.private, aws_route_table_association.public]
}
