# NorthStar Churn Model - Deployment Plan

Endpoint `northstar-churn-prod` (us-east-1), account 761641207876. Run every command from the repo root in a bash shell with AWS credentials for that account. `B=northstar-dev-data-761641207876` is the data bucket.

## 1. Deployment strategy and rationale

**Real-time endpoint, canary rollout**: champion `northstar-churn-v8` (weight 9) and canary `northstar-churn-v9` (weight 1) on one endpoint, both `ml.m5.large`.

NorthStar needs churn scores at two frequencies. The retention campaign needs **weekly** scores for the full active base by Monday 6 AM ET. The offer generation system needs a **per-request** score inside its **2-second** response budget, for customers whose last weekly score is up to six days old. A real-time endpoint serves both: the Monday job sends multi-row CSV payloads, and the offer system sends one row per request. Batch Transform covers only the weekly need, and its quota on this account is 0 (`L-236AE59F`), so it would have added a second deployment path with no capacity to run it.

A canary exposes 10% of live traffic to the new version; rollback is a weight change, not a redeploy.

## 2. Pre-deployment checklist

1. CI build for the commit is green, including the model gate (`tests/test_model.py`) and the `bandit` security scan.
2. **Model approval, performed by the ML Lead.** The ML Lead reads `evaluation_metrics.json` for each package and approves it only if every gate passes. For this release, v8 and v9: precision_top10 0.7167 (gate 0.50), recall_top10 0.3258 (gate 0.25), lift 95% CI [0.0451, 0.0840] (must exclude 0). AUC was 0.7854 against a 0.7208 recency baseline. Approval was recorded on 2026-11-13:
   ```bash
   aws sagemaker update-model-package --model-package-arn arn:aws:sagemaker:us-east-1:761641207876:model-package/northstar-churn-models/8 \
     --model-approval-status Approved --approval-description "Approved by ML Lead ..."
   ```
3. Endpoint quota checked: `aws service-quotas get-service-quota --service-code sagemaker --quota-code L-614B09FD` returns at least 2 (it is 30).
4. The MLEngineer role has the `S3DataCaptureWrite` statement (`infrastructure/modules/iam/main.tf`).
5. MLOps on-call has reviewed `deployment/configs/` and covers the window.

Deploy:
```bash
ROLE=arn:aws:iam::761641207876:role/northstar-dev-MLEngineer
for v in 8 9; do aws sagemaker create-model --model-name northstar-churn-v$v --execution-role-arn $ROLE \
  --primary-container ModelPackageName=arn:aws:sagemaker:us-east-1:761641207876:model-package/northstar-churn-models/$v; done
aws sagemaker create-endpoint-config --cli-input-json file://deployment/configs/endpoint-config-canary.json
aws sagemaker create-endpoint --endpoint-name northstar-churn-prod --endpoint-config-name northstar-churn-canary-config
aws sagemaker wait endpoint-in-service --endpoint-name northstar-churn-prod
aws application-autoscaling register-scalable-target --cli-input-json file://deployment/configs/scalable-target.json
aws application-autoscaling put-scaling-policy --cli-input-json file://deployment/configs/scaling-policy.json
aws cloudwatch put-metric-alarm --cli-input-json file://deployment/configs/rollback-alarm.json
```

## 3. Rollback criteria

- **Metric:** `AWS/SageMaker` `ModelLatency`, statistic **p95**, dimensions `EndpointName=northstar-churn-prod`, `VariantName=canary`.
- **Threshold:** greater than **200000 microseconds (200 ms)** for **3 consecutive 1-minute periods**. Alarm `northstar-churn-rollback-canary-latency`, defined in `deployment/configs/rollback-alarm.json`. Observed p95 is about 10 ms (10255 µs), and 200 ms leaves 1.8 s of the offer system's 2 s budget.
- **Who decides:** the MLOps on-call engineer rolls back as soon as the alarm reaches `ALARM`, without waiting for approval, and then informs the ML Lead. Any `Invocation5XXErrors` on the canary also justifies a rollback.
- **Action:** `bash deployment/configs/rollback-action.sh` sets the canary weight to 0. It takes about 90 seconds, drops no requests, and does not stop billing.

## 4. Monitoring window

**Production:** 48 hours at 9:1, then promote the canary to 100%. **This lab:** 60 minutes, then roll back so the control is exercised. Throughout the window, watch canary p95 latency, `Invocation5XXErrors` and invocation counts per variant, and confirm that `.jsonl` files appear under `s3://$B/datacapture/`.

**Clean** means: the alarm never reached `ALARM`, zero 5XX errors, and the observed split matches the weights. Lab result: 1358 calls, 9.8% canary, 0 errors, p95 8.4 ms, alarm stayed `OK`; rolled back to exercise the control.

What 60 minutes cannot catch, and 48 hours can: a full daily traffic cycle, the nightly POS batch and feature refresh, a scale-out followed by the 600-second scale-in, slow memory or latency creep, and enough canary volume to compare score distributions. A real rollout would also compare canary and champion score distributions from data capture, and offer acceptance for customers the canary scored.

Auto-scaling: target tracking on `SageMakerVariantInvocationsPerInstance` at 1000, 1 to 2 instances. Scale-out cooldown 60 seconds for the Monday surge; scale-in cooldown 600 seconds to avoid oscillation.

## 5. Stakeholder notifications

| Role | Deployment start | Promotion | Rollback |
| --- | --- | --- | --- |
| ML Lead | Start time, versions, approval record | Promotion confirmation with window metrics | Immediate page: alarm, time, metrics |
| MLOps on-call | Runs the deployment, owns the window | Runs the promotion | Runs the rollback, opens an incident |
| VP of Marketing (retention campaign owner) | Heads-up that scores may come from two versions | New version is live for Monday scoring | Champion still serving; campaign unaffected |
| Offer-system engineering lead | Start time and endpoint name | Promotion notice | Rollback notice and latency data |
| Chief Privacy Officer | Data capture enabled, 7-day retention | None | None |
| VP of Technology | Change-calendar entry | Change closed | Incident summary |

## 6. Post-deployment review

Within 2 business days of promotion or rollback. Attendees: ML Lead, MLOps on-call, offer-system engineering lead, VP of Marketing delegate. The output is `docs/postmortems/<date>-churn-<version>.md`, containing a metrics snapshot, the observed split, the decision, timings, and action items with owners.

## 7. Resource cleanup

After the window closes, delete resources in this order: scaling policy, scalable target, rollback alarm, endpoint (this stops billing), endpoint config, SageMaker models.
```bash
bash scripts/teardown-lab5.sh
```
The script verifies against the live API (not the console, which lags by hours) and writes `docs/lab5-teardown-output.txt`; all six checks must read `OK`. Model Registry packages are kept.
