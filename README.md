# NorthStar AI Platform

CS 401R course project: the shared AWS platform backing NorthStar Retail's
three AI systems (churn prediction, offer generation, customer service
agent), built incrementally lab by lab as Terraform-managed infrastructure.

## What's here

| Lab | Adds |
|---|---|
| Lab 1 | VPC (public subnet only), S3 data lake bucket, `MLEngineer` IAM role, SageMaker Studio domain |
| Lab 2 | Private subnet + NAT Gateway (Studio moved off the public subnet), `DataEngineer` + `ModelMonitor` IAM roles, S3 lifecycle rules, a Glue ingestion/feature-engineering pipeline, and a SageMaker Feature Store |

## Repo layout

```
infrastructure/
  modules/
    vpc/            VPC, public + private subnets, IGW, NAT Gateway, route tables, security groups
    storage/        S3 data bucket, prefixes, encryption/versioning, lifecycle rules
    iam/            MLEngineer, DataEngineer, ModelMonitor roles + policies
    sagemaker/      SageMaker Studio domain + user profile
    glue/           Glue catalog database, raw-data crawler, transform + feature-engineer jobs
    feature_store/  SageMaker Feature Group (customer-features)
  environments/
    dev/            real AWS deployment (S3 + DynamoDB remote state)
    local/          LocalStack deployment (vpc/storage/iam only — no NAT, no Glue/SageMaker)
glue-scripts/        PySpark ETL scripts run by the Glue jobs
scripts/              bootstrap-state.sh, verify-lab1.sh, verify-lab2.sh, teardown-lab2.sh, check-secrets.sh
docs/                 submission evidence (screenshots, verification output, ADR, cost estimate, data contract, lineage diagram)
```

## Deploying (real AWS)

```bash
bash scripts/bootstrap-state.sh        # one-time: creates the Terraform state bucket + lock table
cd infrastructure/environments/dev
terraform init
terraform plan
terraform apply
```

This provisions the VPC (public + private subnets, NAT Gateway), the S3
data bucket with lifecycle rules, all three IAM roles, the SageMaker Studio
domain (in the private subnet), the Glue catalog/crawler/jobs, and the
Feature Store feature group.

## Running the data pipeline end-to-end (Lab 2)

Once `terraform apply` has finished:

```bash
# 1. Upload sample transaction data to the raw zone
aws s3 cp northstar-raw-sample.csv \
  s3://northstar-dev-data-$(aws sts get-caller-identity --query Account --output text)/raw/customers/northstar-raw-sample.csv

# 2. Crawl raw/ to register its schema in the Glue Data Catalog
aws glue start-crawler --name northstar-dev-raw-crawler
aws glue get-crawler --name northstar-dev-raw-crawler --query 'Crawler.State'

# 3. Transform: raw/customers/ -> processed/customers/ (type casting, null
#    imputation, dedup — see glue-scripts/transform.py)
aws glue start-job-run --job-name northstar-dev-transform

# 4. Feature engineering: processed/customers/ -> features/customers/ +
#    SageMaker Feature Store (RFM features, loyalty tier, churn label —
#    see glue-scripts/feature_engineer.py)
aws glue start-job-run --job-name northstar-dev-feature-engineer

# 5. Verify
bash scripts/verify-lab2.sh
```

`scripts/verify-lab2.sh` checks both job run statuses, the catalog table,
the processed/feature Parquet output's data quality, and the Feature
Group's definitions and a live `GetRecord` round trip.

## LocalStack validation (no AWS cost)

```bash
make local-validate LOCAL_OUT=docs/lab2-localstack-output.txt
```

Applies `vpc`, `storage`, and `iam` against LocalStack Community (`glue`,
`feature_store`, and `sagemaker` are real-AWS only — LocalStack Community
doesn't emulate SageMaker or NAT Gateways). Confirms all 3 IAM roles exist,
the VPC/subnets are correct, and no NAT Gateway was created.

## Tearing down

```bash
bash scripts/teardown-lab2.sh
```

`terraform destroy` alone does not fully tear down Lab 2 — six resources
(orphaned Glue ENIs, the SageMaker Studio EFS filesystem, auto-created NFS
security groups, S3 object versions, the Feature Store's Glue database, and
SageMaker lineage contexts/artifacts) are created outside Terraform's state
and survive a plain `destroy`. `teardown-lab2.sh` handles all of them in
order and verifies nothing billable remains — see the script for details on
why each one exists. Run this after submitting; the NAT Gateway alone bills
whether or not it's used.
