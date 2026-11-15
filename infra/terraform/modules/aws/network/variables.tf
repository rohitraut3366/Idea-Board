variable "name" {
  description = "Prefix for network resources."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 VPC range; use a /16 to allocate /24 subnets."
  type        = string

  validation {
    condition     = try(cidrnetmask(var.vpc_cidr) == "255.255.0.0", false)
    error_message = "Use an IPv4 /16 VPC range; the module allocates /24 subnets."
  }
}

variable "availability_zones" {
  description = "Two or three availability zones in the selected region."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2 && length(var.availability_zones) <= 3 && length(distinct(var.availability_zones)) == length(var.availability_zones)
    error_message = "Provide two or three distinct availability zones."
  }
}
