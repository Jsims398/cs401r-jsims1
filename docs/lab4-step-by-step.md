# Lab 4 Step-by-Step Guide

Repo-specific. Checked current state 2026-10-27:
- `models/churn/churn_training_skeleton.py` — your Lab 3 training code (972 lines). Source for Task 1's `train()`.
- `glue-scripts/feature_engineer.py` — Lab 2 PySpark job. Source for the pandas port.
- `cs401r-lab4-template-main/` — starter kit, **not yet merged into repo root.** Root has no `pytest.ini`, `buildspec.yml`, `pipeline.yaml`, `requirements.txt`, `data/`, or populated `tests/test_data.py` etc.
- `model/model.xgb`, `model/model_metadata.json` — local Lab 3 artifacts, fine as a reference but not what CI will produce.

Due Sat Oct 31, midnight. ~8 steps, roughly in dependency order.

---

## Step 0 — Merge starter kit into repo root

```bash
cp cs401r-lab4-template-main/buildspec.yml .
cp cs401r-lab4-template-main/pipeline.yaml .
cp cs401r-lab4-template-main/requirements.txt .
cp cs401r-lab4-template-main/pytest.ini .
cp cs401r-lab4-template-main/tests/conftest.py tests/
cp cs401r-lab4-template-main/tests/test_data.py tests/
cp cs401r-lab4-template-main/tests/test_features.py tests/
cp cs401r-lab4-template-main/tests/test_model.py tests/
cp cs401r-lab4-template-main/models/churn/pipeline_definition.py models/churn/
cp cs401r-lab4-template-main/models/churn/train_sagemaker.py models/churn/
cp cs401r-lab4-template-main/models/churn/churn_model.py models/churn/
```
Do not overwrite `churn_training_skeleton.py` — it stays as reference/Lab 3 record. `churn_model.py` is the new file you edit for Lab 4. Check `.gitignore` still excludes secrets after the copy. Commit this merge before touching logic.

## Step 1 — Six prerequisites (infra, one-time)

In order, from `lab4-instructions.md` "Before you deploy anything":

1. Create **versioned** CI artifacts bucket (`northstar-dev-cicd-artifacts-<account>`) — separate from your data bucket.
2. Create GitHub CodeStar connection, authorize it in console, confirm `AVAILABLE` before moving on.
3. (Done in Steps 2-3 below) `churn_model.py` implemented + pipeline defined.
4. Add `iam:PassRole` statement (`PassSelfToSageMaker`, condition on `sagemaker.amazonaws.com`) to MLEngineer policy in `infrastructure/modules/iam/main.tf`, confirm `sagemaker:AddTags`/`sagemaker:ListTags` present, `terraform apply`.
5. Confirm Lab 2 stack up and feature job ran in last 48h: `aws glue start-job-run --job-name northstar-dev-feature-engineer`. Re-run at start of any session you push in.
6. Confirm spot quota ≥1: `aws service-quotas get-service-quota --service-code sagemaker --quota-code L-29688C85 --query 'Quota.Value' --output text`.

Deploy pipeline stack later (Step 5) with `CAPABILITY_NAMED_IAM`, not before `churn_model.py` works locally.

## Step 2 — Port feature engineering to pandas (`data/feature_engineering.py`)

`tests/test_features.py` imports `compute_recency_features`, `compute_frequency_features`, `compute_monetary_features`, `compute_behavioral_features`, `build_churn_feature_set` from `data/feature_engineering.py` — doesn't exist yet. Port the logic out of `glue-scripts/feature_engineer.py` (PySpark) into pure pandas functions, same windows/definitions. Watch the one gotcha the test file calls out: `avg_basket_size_6m` is **items per order** over 180d, not dollars.

Run `pytest tests/test_features.py -v` until the ≥5 required cases pass (normal/boundary/zero-purchase/single-transaction — there are two `TODO`s left in the fixture body for the zero-transaction sentinel and null-check assertion; fill those in).

## Step 3 — Implement `train()` in `models/churn/churn_model.py`

Copy (don't import) logic from `churn_training_skeleton.py`:
- `preprocess_features` → X, y
- `train_test_split(test_size=0.30, random_state=seed, stratify=y)` — pass `loyalty_tier` as Series/object array, not `.values`
- `train_model` → XGBoost
- `train_recency_baseline`
- `evaluate_model` → metrics dict, must include `precision_top10`, `recall_top10`, `lift_ci_low`, `lift_ci_high` (your Lab 3 `evaluate_model()` already returns these)
- Keep the gate-failure `raise` from Lab 3 intact — a bad model must fail training, not just the CI test
- No `mlflow`/`sagemaker` imports at top of file
- Return `(booster, metrics)` — `xgb.Booster`, not `XGBClassifier` (call `.get_booster()` if needed)

Test locally before any push:
```bash
pip install -r requirements.txt
mkdir -p /tmp/channel && aws s3 cp s3://<your-data-bucket>/features/customers/ /tmp/channel/ --recursive
python models/churn/train_sagemaker.py --train-channel /tmp/channel \
  --model-dir /tmp/model --output-data-dir /tmp/out
cp /tmp/out/model_metadata.json /tmp/model/
EVAL_METRICS_PATH=/tmp/out/evaluation_metrics.json \
  pytest tests/test_model.py --model-path /tmp/model/xgboost-model
```

## Step 4 — Finish `tests/test_data.py` + add `tests/test_fairness.py`

`test_data.py` is already complete except two `TODO`s at the bottom of `TestFeatures`:
- No-post-cutoff-leakage test (recompute recency/tenure/frequency from `processed/` rows filtered to `purchase_date <= FEATURE_CUTOFF`, assert equal to what's in `features/`)
- Freshness test: latest `event_time` < 48h old

Write `tests/test_fairness.py` from scratch (no template given): slice recall by `loyalty_tier`, flag (don't fail) if gap between highest/lowest tier > 10pp. Reads `EVAL_METRICS_PATH`, so have `train()`'s metrics dict include a per-tier breakdown.

Run full local suite:
```bash
pytest tests/ -v
```

## Step 5 — Deploy CI/CD stack, verify green run

```bash
aws cloudformation deploy --template-file pipeline.yaml --stack-name northstar-cicd \
  --parameter-overrides ProjectName=northstar Environment=dev \
    GitHubOwner=YOUR_GITHUB_USERNAME GitHubRepo=cs401r-<your-netid> \
    GitHubBranch=main ArtifactsBucket="$AB" \
    GitHubConnectionArn=<arn> \
    SageMakerRoleArn=$(terraform -chdir=infrastructure/environments/dev output -raw ml_engineer_role_arn) \
  --capabilities CAPABILITY_NAMED_IAM
```
Push to `main` first — stack creation triggers an immediate run. Subscribe an email to the `northstar-model-approvals` SNS topic and confirm the link. Get one green run, then approve its package (becomes champion for regression test):
```bash
aws sagemaker update-model-package --model-package-arn <arn> --model-approval-status Approved
```

## Step 6 — Failure/recovery demo (alarm evidence)

Define `snap()` and `TOPIC` from the instructions doc. Then:
1. `snap "BEFORE"` (alarm `OK`, note newest package version)
2. Push a deliberately failing test, wait for build fail + alarm `ALARM` (~2min), `snap "AFTER FAILED RUN"`, save `docs/lab4-build-failed.log`, screenshot alarm email → `docs/lab4-alarm-email.png`
3. Revert, push, wait for green + alarm `OK`, `snap "AFTER REVERT"` — this is your **final green run**

Keep both commits in `main` history.

## Step 7 — Lineage + MLflow evidence (Task 3)

- `update-model-package --customer-metadata-properties` on final green run's package (commit SHA, training data S3 URI+timestamp) → `docs/lab4-model-package.json`
- `docs/lab4-mlflow-runs.txt`: ≥3 MLflow App runs with differing hyperparameters, full (untruncated) `params.*`/`metrics.*` columns

## Step 8 — Write `docs/lab4-xops-assessment.md`

Required headings: `## Pipeline Stage Mapping`, `## Champion-Challenger`, `## Retraining Triggers`, `## DataOps Maturity`, `## MLOps Maturity`. Champion-challenger criterion must be numeric/binary. Each retraining trigger needs a threshold/schedule + naming the AWS service. Maturity sections cite specific repo files/evidence, not generic claims; ~400 words total, structure per instructions.

## Step 9 — Capture evidence, teardown, submit

Run the capture block (`docs/lab4-pipeline-runs.txt`, `docs/lab4-build-green.log`, `docs/lab4-model-registry.json`) **while stack is still up** — nothing regenerates after teardown. Open and sanity-check every file before deleting anything.

```bash
aws cloudformation delete-stack --stack-name northstar-cicd
aws cloudformation wait stack-delete-complete --stack-name northstar-cicd
aws s3api delete-bucket --bucket "$AB"   # empty versions first
aws logs delete-log-group --log-group-name /aws/codebuild/northstar-ci
bash scripts/teardown-lab2.sh
```
Set any `Approved` package to `Rejected` before the data bucket goes. Then:
```bash
git add docs/ tests/ models/ data/ buildspec.yml pipeline.yaml pytest.ini requirements.txt
git commit -m "..."
git tag lab4-submit
git push origin lab4-submit
git push origin main
```
Submit repo URL in Canvas.

---

## Evidence checklist (exact filenames)

- `tests/test_data.py`, `test_features.py`, `test_model.py`, `test_fairness.py`
- `models/churn/churn_model.py`
- `buildspec.yml`, `pipeline.yaml`
- `docs/lab4-build-green.log`
- `docs/lab4-build-failed.log`
- `docs/lab4-pipeline-runs.txt`
- `docs/lab4-failure-demo.txt`
- `docs/lab4-alarm-email.png`
- `docs/lab4-model-registry.json`
- `docs/lab4-model-package.json`
- `docs/lab4-mlflow-runs.txt`
- `docs/lab4-xops-assessment.md`
- Deliberate-failure commit + its revert, both in `main` history
