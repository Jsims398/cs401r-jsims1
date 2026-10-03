# ── modules/vpc ──────────────────────────────────────────────────────────────
# Required resources (Task B1). Only these belong in this module:
#
#   aws_vpc
#   aws_subnet                      public only in Lab 1
#   aws_internet_gateway
#   aws_route_table
#   aws_route_table_association
#   aws_security_group
#
# Name everything from var.project and var.environment. A hardcoded
# project-environment literal anywhere under modules/ fails the rubric grep.
#
# Example of the naming pattern expected:
#
#   resource "aws_vpc" "this" {
#     cidr_block = var.vpc_cidr
#     tags       = { Name = "${var.project}-${var.environment}-vpc" }
#   }

# TODO: implement the six resources above.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "${var.project}-${var.environment}-vpc" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.project}-${var.environment}-public-1" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-${var.environment}-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = { Name = "${var.project}-${var.environment}-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "this" {
  name        = "${var.project}-${var.environment}-sagemaker-sg"
  description = "SageMaker Studio traffic, VPC-internal only"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "All traffic from within the VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-sagemaker-sg" }
}

resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.project}-${var.environment}-private-1" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  count  = var.enable_nat_gateway ? 1 : 0
  tags   = { Name = "${var.project}-${var.environment}-nat-eip" }
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public.id
  count         = var.enable_nat_gateway ? 1 : 0
  tags          = { Name = "${var.project}-${var.environment}-nat-gateway" }
}

resource "aws_route_table" "private" {
  count  = var.enable_nat_gateway ? 1 : 0
  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[0].id
  }

  tags = { Name = "${var.project}-${var.environment}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = var.enable_nat_gateway ? 1 : 0
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private[0].id
}