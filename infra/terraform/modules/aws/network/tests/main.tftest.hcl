mock_provider "aws" {
  override_during = plan
  mock_resource "aws_subnet" {
    defaults = { id = "subnet-11111111" }
  }
  mock_resource "aws_internet_gateway" {
    defaults = { id = "igw-11111111" }
  }
  mock_resource "aws_nat_gateway" {
    defaults = { id = "nat-11111111" }
  }

}

variables {
  name               = "idea-board-test"
  vpc_cidr           = "10.10.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "configuration" {
  command = plan

  assert {
    condition     = length(aws_subnet.private) == 2 && length(aws_subnet.public) == 2
    error_message = "Create public and private subnets in both zones."
  }

  assert {
    condition     = alltrue([for subnet in aws_subnet.private : !subnet.map_public_ip_on_launch])
    error_message = "Worker and database subnets must not assign public addresses."
  }

  assert {
    condition     = aws_subnet.public["us-east-1a"].cidr_block == "10.10.0.0/24" && aws_subnet.private["us-east-1a"].cidr_block == "10.10.128.0/24"
    error_message = "Public and private ranges must be separate."
  }

  assert {
    condition     = aws_route.nat.nat_gateway_id == aws_nat_gateway.this.id && aws_route.internet.gateway_id == aws_internet_gateway.this.id
    error_message = "Private egress uses NAT; public egress uses the internet gateway."
  }

  assert {
    condition     = toset(output.private_subnet_ids) == toset([for subnet in aws_subnet.private : subnet.id])
    error_message = "Only private subnets are exported to workers and PostgreSQL."
  }
}

run "reject_single_zone" {
  command = plan
  variables {
    availability_zones = ["us-east-1a"]
  }
  expect_failures = [var.availability_zones]
}
