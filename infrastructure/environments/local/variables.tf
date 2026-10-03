variable "project" {
  description = "Project name, used as the first element of every resource name"
  type        = string
  default     = "northstar"
}

variable "environment" {
  description = "Deployment environment — fixed to local so names never collide with dev"
  type        = string
  default     = "local"
}

variable "aws_region" {
  description = "Region LocalStack emulates; must match awslocal's default"
  type        = string
  default     = "us-east-1"
}

variable "enable_nat_gateway" {
  description = "Whether to enable a NAT gateway for the private subnet"
  type        = bool
  default     = false
}

variable "enable_lifecycle_rules" {
  description = "Whether to enable lifecycle rules"
  type        = bool
  default     = false
}