variable "project" {
  description = "Project name, used as the first element of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "bucket_name" {
  description = "Data bucket backing the offline store (features/offline-store/ prefix)"
  type        = string
}

variable "execution_role_arn" {
  description = "IAM role Feature Store assumes to write records (the DataEngineer role — its trust policy must include sagemaker.amazonaws.com)"
  type        = string
}
