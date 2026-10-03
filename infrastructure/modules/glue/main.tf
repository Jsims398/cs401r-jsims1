# ── modules/glue ─────────────────────────────────────────────────────────────
# Catalog database, raw-data crawler, and the two ETL jobs (transform,
# feature-engineer). Job workers run inside the private subnet, which means
# every job needs a Glue NETWORK connection — see the security group below
# for the specific "self-referencing all ports" requirement AWS enforces
# that a VPC-CIDR-sourced rule does not satisfy.

resource "aws_glue_catalog_database" "this" {
  name = "${var.project}_${var.environment}" #northstar_dev
}

# Glue requires at least one attached security group with an all-ports
# ingress rule sourced from itself (self = true). A rule sourced from the
# VPC CIDR looks equivalent but is rejected at connection-provisioning time
# with "At least one security group must open all ingress ports."
resource "aws_security_group" "glue" {
  name        = "${var.project}-${var.environment}-glue-sg"
  description = "Glue job network connection - self-referencing all ports required by AWS"
  vpc_id      = var.vpc_id

  ingress {
    description = "All traffic from within this security group (Glue requirement)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-glue-sg" }
}

resource "aws_glue_connection" "vpc" {
  name            = "${var.project}-${var.environment}-glue-connection"
  connection_type = "NETWORK"

  physical_connection_requirements {
    subnet_id              = var.private_subnet_id
    security_group_id_list = [aws_security_group.glue.id]
    availability_zone      = var.availability_zone
  }
}

resource "aws_s3_object" "transform_script" {
  bucket = var.bucket_name
  key    = "artifacts/glue/transform.py"
  source = "${path.module}/../../../glue-scripts/transform.py"
  etag   = filemd5("${path.module}/../../../glue-scripts/transform.py")
}

resource "aws_s3_object" "feature_engineer_script" {
  bucket = var.bucket_name
  key    = "artifacts/glue/feature_engineer.py"
  source = "${path.module}/../../../glue-scripts/feature_engineer.py"
  etag   = filemd5("${path.module}/../../../glue-scripts/feature_engineer.py")
}

resource "aws_glue_crawler" "raw" {
  name          = "${var.project}-${var.environment}-raw-crawler"
  role          = var.data_engineer_role_arn
  database_name = aws_glue_catalog_database.this.name

  s3_target {
    path = "s3://${var.bucket_name}/raw/customers/"
  }

  tags = { Name = "${var.project}-${var.environment}-raw-crawler" }
}

resource "aws_glue_job" "transform" {
  name              = "${var.project}-${var.environment}-transform"
  role_arn          = var.data_engineer_role_arn
  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"
  connections       = [aws_glue_connection.vpc.name]

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket_name}/${aws_s3_object.transform_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--database_name" = aws_glue_catalog_database.this.name
    "--table_name"    = "customers"
    "--output_path"   = "s3://${var.bucket_name}/processed/customers/"
    "--job-language"  = "python"
  }

  tags = { Name = "${var.project}-${var.environment}-transform" }
}

resource "aws_glue_job" "feature_engineer" {
  name              = "${var.project}-${var.environment}-feature-engineer"
  role_arn          = var.data_engineer_role_arn
  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"
  connections       = [aws_glue_connection.vpc.name]

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket_name}/${aws_s3_object.feature_engineer_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--input_path"                = "s3://${var.bucket_name}/processed/customers/"
    "--output_path"               = "s3://${var.bucket_name}/features/customers/"
    "--feature_group_name"        = var.feature_group_name
    "--region"                    = var.aws_region
    "--job-language"              = "python"
    "--additional-python-modules" = "boto3"
  }

  tags = { Name = "${var.project}-${var.environment}-feature-engineer" }
}
