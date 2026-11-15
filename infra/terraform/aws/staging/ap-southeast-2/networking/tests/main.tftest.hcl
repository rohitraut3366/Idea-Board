mock_provider "aws" {
  override_during = plan

  mock_resource "aws_subnet" { defaults = { id = "subnet-11111111" } }
  mock_resource "aws_internet_gateway" { defaults = { id = "igw-11111111" } }
  mock_resource "aws_nat_gateway" { defaults = { id = "nat-11111111" } }
}

variables {
  name               = "idea-board-test"
  region             = "us-east-1"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "configuration" {
  command = plan
  assert {
    condition     = length(output.private_subnet_ids) == 2
    error_message = "Publish the private networking contract for dependent projects."
  }
}
