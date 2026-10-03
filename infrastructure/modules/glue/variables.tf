variable "project" {
  description = "Project name, used as the first element of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "Region for the feature-engineer job's Feature Store runtime client"
  type        = string
}

variable "vpc_id" {
  description = "VPC the Glue NETWORK connection attaches to"
  type        = string
}

variable "private_subnet_id" {
  description = "Private subnet Glue job workers run in"
  type        = string
}

variable "availability_zone" {
  description = "Availability zone of the private subnet (required by the Glue connection's physical_connection_requirements)"
  type        = string
}

variable "bucket_name" {
  description = "Name of the data bucket (raw/processed/features/artifacts prefixes)"
  type        = string
}

variable "data_engineer_role_arn" {
  description = "ARN of the DataEngineer role — runs the crawler and both ETL jobs"
  type        = string
}

variable "feature_group_name" {
  description = "Name of the SageMaker Feature Group the feature-engineer job writes records to"
  type        = string
}
