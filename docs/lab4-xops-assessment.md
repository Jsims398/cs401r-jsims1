# Lab 4 XOps Assessment — NorthStar Churn Model

## Pipeline Stage Mapping

Implementation: **AWS CodePipeline + CodeBuild** (`pipeline.yaml`, `buildspec.yml`). Chosen over GitHub Actions because every downstream resource (SageMaker Pipelines, Model Registry, CloudWatch, SNS) is in the same AWS account, so the build authenticates with an IAM role instead of long-lived keys stored in GitHub secrets.

| Required phase | CodePipeline stage | Where it runs |
| --- | --- | --- |
| 1. Source | Source | CodeStar connection to `Jsims398/cs401r-jsims1`, branch `main` |
| 2. Test | Build | `buildspec.yml` `pre_build`: `tests/test_data.py`, `tests/test_features.py`. A failure stops the build before anything trains (`docs/lab4-failure-demo.txt`, AFTER FAILED RUN: `PRE_BUILD FAILED`, no BUILD phase) |
| 3. Build | Build | `build`: `models/churn/pipeline_definition.py --upsert` packages `models/churn/` and runs a spot SageMaker training job that calls `churn_model.train()` |
| 4. Evaluate | Build | Inside training, `evaluate_model()` raises if precision@10% < 0.50, recall@10% < 0.25 or the lift CI includes 0, so a failing model never registers. CodeBuild then runs `tests/test_model.py` and `tests/test_fairness.py` against the emitted metrics |
| 5. Register | Build, then ManualApproval | SageMaker Pipeline `RegisterModel` step → `PendingManualApproval` in `northstar-churn-models`. `post_build` rejects the package if a later test fails. The ManualApproval stage emails the approver through SNS |

Three stages, not five: a CodePipeline stage is a hand-off boundary, and Test → Evaluate need no hand-off, so they share one CodeBuild job and one artifact.

## Champion-Challenger

A challenger replaces the champion (newest `Approved` package) **if and only if all of these hold**:

1. It passed every CI gate: precision@10% ≥ 0.50, recall@10% ≥ 0.25, lift-over-recency 95% CI lower bound > 0.
2. **Challenger AUC − champion AUC ≥ +0.010**, measured on the same 30% stratified validation split (`random_state=42`).
3. Top-10% recall for the Platinum and Gold tiers is not lower than the champion's.

CI enforces a separate, looser floor: `tests/test_model.py::TestChampionRegression` fails the build if challenger AUC < champion AUC − 0.02. That floor blocks regressions. The +0.010 bar decides replacement. Example: v7 (`docs/lab4-build-green.log`: `champion v6 auc=0.7854; candidate auc=0.7854`) passed the floor but does not clear +0.010, so it stays `PendingManualApproval` and v6 remains champion.

## Retraining Triggers

**(a) Scheduled, weekly.** An **Amazon EventBridge Scheduler** schedule `cron(0 5 ? * MON *)` starts the Glue job `northstar-dev-feature-engineer`. A second schedule at `cron(0 6 ? * MON *)` calls CodePipeline `StartPipelineExecution` on `northstar-pipeline`. The one-hour gap keeps `test_features_are_fresh` (48 h limit) green.

**(b) Performance-based.** Churn labels mature 90 days after scoring. A weekly **SageMaker Model Monitor** model-quality job joins the champion's predictions with matured labels and publishes `auc` to **CloudWatch**. A CloudWatch alarm fires when **production AUC < 0.74 for 2 consecutive weekly datapoints**. 0.74 is the champion's 0.785 minus 0.045, the lower edge of its lift over the recency baseline, so below it the model is barely beating the free rule. An **EventBridge** rule on the alarm's `ALARM` state starts `northstar-pipeline`. A data-quality job on the same monitor also fires the rule if the PSI of `days_since_last_purchase` exceeds 0.2.

## DataOps Maturity

**Current level: 2**

**Evidence:**
- All infrastructure is code: Terraform modules (`infrastructure/modules/glue/`, `infrastructure/modules/iam/`).
- The ETL is a versioned Glue job (`glue-scripts/feature_engineer.py`), and its logic is unit tested through a pandas port (`data/feature_engineering.py`, 18 tests in `tests/test_features.py`).
- Data tests gate every build. `tests/test_data.py` checks schema, grain, nulls, no post-cutoff leakage (recomputes recency and frequency from pre-cutoff rows, which must match exactly) and 48-hour freshness. `docs/lab4-build-green.log`: `28 passed`.
- The freshness test is not theoretical: it failed locally on the 16-day-old feature set (389.6 h) until the Glue job was re-run.

**Gap to Level 3:** Data production is not automated. The Glue job runs only when started by hand, so freshness is detected (the build fails) rather than guaranteed. There is no orchestration linking a new raw drop to the feature job. Terraform state also drifted when the NAT gateway was deleted outside Terraform, and nothing detected it until the Glue job failed on the missing route.

**Top priority investment:** Add an `aws_glue_trigger` of type `SCHEDULED` to `infrastructure/modules/glue/`, plus a nightly `terraform plan -detailed-exitcode` drift check in CodeBuild that alerts through the existing `northstar-model-approvals` SNS topic.

## MLOps Maturity

**Current level: 2**

**Evidence:**
- Training, evaluation and registration are automated and gated (`buildspec.yml`, `models/churn/pipeline_definition.py`, `models/churn/churn_model.py`).
- Behavioural tests catch what aggregate metrics miss. The recency-monotonicity test in `tests/test_model.py` failed an unconstrained model, which led to the monotone constraint in `churn_model.py`.
- A failed gate halts the build and notifies: `docs/lab4-failure-demo.txt` shows no new package, the alarm in `ALARM`, and "Successfully executed action"; see also `docs/lab4-alarm-email.png`.
- Lineage is recorded on the package (`docs/lab4-model-package.json`: commit SHA, data URI and timestamp), and experiments are tracked in an MLflow App (`docs/lab4-mlflow-runs.txt`).
- The fairness check surfaces a 0.387 recall gap across tiers to the approver (`tests/test_fairness.py`).

**Gap to Level 3:** Nothing runs after registration. There is no deployed endpoint, no production monitoring and no automated retraining; the triggers above are designed, not deployed. CI also starts by hand, because the CodeStar connection has no GitHub App webhook installed.

**Top priority investment:** Install the AWS Connector for GitHub app so pushes trigger `northstar-pipeline`. Then deploy SageMaker Model Monitor with the CloudWatch → EventBridge retraining rule from *Retraining Triggers (b)*.
