# NorthStar AI Platform

CS 401R course project: the shared AWS platform backing NorthStar Retail's
three AI systems (churn prediction, offer generation, customer service
agent), built incrementally lab by lab as Terraform-managed infrastructure.

## What's here

| Lab | Adds |
|---|---|
| Lab 1 | VPC (public subnet only), S3 data lake bucket, `MLEngineer` IAM role, SageMaker Studio domain |
| Lab 2 | Private subnet + NAT Gateway (Studio moved off the public subnet), `DataEngineer` + `ModelMonitor` IAM roles, S3 lifecycle rules, a Glue ingestion/feature-engineering pipeline, and a SageMaker Feature Store |
| Lab 3 | Track A: XGBoost churn model trained on the Feature Store, tracked in a SageMaker MLflow App, registered in Model Registry. Track B: a RAG pipeline (FAISS + Titan embeddings + Claude Haiku 4.5 via Bedrock) generating retention offers grounded in the policy corpus |

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
models/churn/        Lab 3 Track A: churn_training_skeleton.py (Athena query, XGBoost, MLflow, Model Registry)
rag/                  Lab 3 Track B: RAG pipeline (corpus chunking, FAISS index, retrieval, prompts, generation)
evaluation/           evaluation_harness.py (given, RAGAS/agent test cases) + run_track_b.py (eval driver)
northstar-policy-docs/  Track B's policy corpus (return/shipping/loyalty policy + FAQ)
notebooks/            lab3-demo.ipynb (Track B end-to-end demo, committed with outputs)
tests/                 pytest suite for rag/ (44 tests, no AWS calls required)
scripts/              bootstrap-state.sh, verify-lab1.sh, verify-lab2.sh, teardown-lab2.sh, check-secrets.sh,
                       collect-lab3-evidence.sh, teardown-lab3.sh, smoke_test_rag.py, compare_query_strategies.py,
                       compare_profile_injection.py
docs/                 submission evidence (screenshots, verification output, ADR, cost estimate, data contract,
                       lineage diagram, lab3-evidence/ for Lab 3's training logs, metrics, and RAG eval CSVs)
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

## Training and evaluating the churn model (Lab 3, Track A)

Requires the Lab 2 Feature Store populated (see above) and a SageMaker
MLflow App created once (`aws sagemaker create-mlflow-app`; do **not** use
`create-mlflow-tracking-server`, which bills $0.60/hr whether or not you use it):

```bash
mkdir -p docs/lab3-evidence
python models/churn/churn_training_skeleton.py \
  --artifacts-bucket northstar-dev-data-<account> \
  --mlflow-arn arn:aws:sagemaker:us-east-1:<account>:mlflow-app/app-XXXX \
  --run-name <descriptive-name> \
  --output-data-dir docs/lab3-evidence \
  2>&1 | tee docs/lab3-evidence/train-final.log
```

This runs the Feature Store Athena query locally (prints `Athena
QueryExecutionId`), trains XGBoost with class-imbalance handling, bootstraps
a 95% CI on the lift over a recency-only baseline, evaluates per loyalty
tier, logs the run to the MLflow App, and registers the model in
`northstar-churn-models` as `PendingManualApproval`. Artifacts land in
`docs/lab3-evidence/`: `train-final.log`, `evaluation_metrics.json`,
`slice-evaluation.csv`, `confusion-matrix.png`, `feature-importance.png`.
The written report is `docs/lab3-evaluation-report.md`.

## Generating and evaluating retention offers (Lab 3, Track B)

```bash
pip install -r requirements-track-b.txt    # faiss-cpu, ragas, langchain-aws, pytest, ...
pytest tests/ -v                           # 44 tests, deterministic, no AWS calls
PYTHONPATH=. python scripts/smoke_test_rag.py     # one real offer, real Bedrock calls
```

`rag/pipeline.py`'s `invoke(customer_context, question)` is the RAG
pipeline's entry point: it retrieves policy chunks from a local FAISS index
(built once from `northstar-policy-docs/` and cached under
`rag/index_cache/`, gitignored), assembles a prompt with corrected tier
guidelines, and generates an offer via Claude Haiku 4.5 on Bedrock. To run
the full RAGAS evaluation (costs real Bedrock tokens):

```bash
python evaluation/run_track_b.py --runs 3
```

Writes `docs/lab3-evidence/rag_eval.csv` (per-case faithfulness /
answer_relevancy / context_recall across all runs) and prints per-metric
mean/range with the judge model named. `docs/lab3-evidence/` also holds
`query-strategy-comparison.csv` (the 3-way retrieval comparison),
`profile-injection-ablation.csv` (the measured before/after improvement),
and `track-b-examples.md` (5 examples + 2 documented failure cases). Design
rationale (model choices, the RAG-over-fine-tuning tradeoff) is in
`docs/lab3-model-design.md`.

## Tearing down

```bash
bash scripts/collect-lab3-evidence.sh --track B   # run BEFORE any teardown — exports
                                                    # Athena query, MLflow runs, and the
                                                    # Model Registry entry from AWS
bash scripts/teardown-lab3.sh                      # deletes Lab 3 endpoints/jobs; leaves
                                                    # the MLflow App alone (it's free)
bash scripts/teardown-lab2.sh                      # only once fully done with Lab 3
```

`terraform destroy` alone does not fully tear down Lab 2 — six resources
(orphaned Glue ENIs, the SageMaker Studio EFS filesystem, auto-created NFS
security groups, S3 object versions, the Feature Store's Glue database, and
SageMaker lineage contexts/artifacts) are created outside Terraform's state
and survive a plain `destroy`. `teardown-lab2.sh` handles all of them in
order and verifies nothing billable remains — see the script for details on
why each one exists. Run this after submitting; the NAT Gateway alone bills
whether or not it's used. Tearing down Lab 2's Feature Store also means
re-running the Glue pipeline from scratch (see above) if you come back to
this repo later.
