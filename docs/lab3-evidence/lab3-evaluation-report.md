# Lab 3 — Task 1 Evaluation Report: Churn Prediction Model

**Graded run:** `xgb-depth6-eta0.1` (run_id `039816ea270747419eb13d9105caa6ff` in the `northstar-churn` MLflow experiment) — hyperparameters `max_depth=6, eta=0.1, num_round=200, min_child_weight=5, subsample=0.8, colsample_bytree=0.8`, `scale_pos_weight=3.5448` (derived from the training split: 6,999 train rows, 22.0% positive).

**Data provenance:** 9,999 customers from the Lab 2 Feature Group `northstar-dev-customer-features`, pulled via Athena (`docs/lab3-evidence/train-final.log` has the `QueryExecutionId`), stratified 70/30 split (`random_state=42`) → 6,999 train / 3,000 validation.

**XGBoost version:** 3.4.1 (trained locally). Per the lab handout, the SageMaker training container runs 1.7 and the lab's reference figures were measured on 3.2.0 — absolute numbers are not expected to match either to four decimal places, only to agree in direction (lift CI excludes zero either way).

## Evaluation Table

| Metric | Value | Threshold | Result |
|---|---|---|---|
| AUC-ROC (test set) | 0.7773 | report only — no fixed threshold | — |
| Precision @ top 10% | 0.7133 | ≥ 0.50 | ✓ PASS |
| Recall @ top 10% | 0.3242 | ≥ 0.25 | ✓ PASS |
| AUC lift over recency-only baseline | +0.0541 | 95% CI must exclude zero | ✓ PASS |
| Recency-only baseline AUC | 0.7232 | — | — |
| Lift 95% CI | [0.0344, 0.0737] | excludes 0 | ✓ PASS |

The baseline is a model trained on `days_since_last_purchase` alone, trained on the identical training rows and scored on the identical validation rows as the full model. The 95% CI on (full AUC − baseline AUC) was computed by bootstrapping the validation set with replacement 2,000 times, scoring both models on each paired resample, and taking the 2.5th/97.5th percentiles of the difference.

**Interpretation:** the full feature set does measurably better than recency alone — the interval excludes zero by a comfortable margin (lower bound +0.034), so this isn't a result that could plausibly be shuffle luck. The lift itself (+0.054) is modest in absolute terms, which is expected: about a third of churners in this dataset look recency-healthy right up to the cutoff, and it's precisely those customers the behavioral features (category diversity, channel mix, basket size) are meant to catch — a small-but-real lift over recency is the signature of a model actually using them, not of weak feature engineering.

## Hyperparameter Comparison (3 distinct configurations, 5 logged runs)

| Run | depth / eta / rounds | AUC-ROC | Precision@10% | Recall@10% | Lift | Lift 95% CI |
|---|---|---|---|---|---|---|
| **xgb-depth6-eta0.1 (graded)** | 6 / 0.1 / 200 | **0.7773** | 0.7133 | **0.3242** | +0.0541 | [0.0344, 0.0737] |
| xgb-depth4-eta0.2-shallow | 4 / 0.2 / 100 | 0.7729 | 0.7000 | 0.3182 | +0.0497 | [0.0305, 0.0697] |
| xgb-depth8-eta0.05-deep | 8 / 0.05 / 400 | 0.7808 | 0.7067 | 0.3212 | +0.0576 | [0.0372, 0.0777] |

(`xgb-depth6-eta0.1` was logged 3 times across reruns while debugging evidence capture; all three runs are byte-identical in metrics since the pipeline is deterministic given the fixed seed — only one is treated as "the" graded run.)

The spread across configurations is tiny: 0.0079 AUC between the best (deep) and worst (shallow) run, and every CI overlaps heavily with the others. Going deeper (8) over the default (6) buys essentially nothing; going shallower (4) loses almost nothing. That ceiling is itself informative: on ~7,000 training rows and 11 features, the model saturates quickly, and there isn't enough data or feature interaction complexity for extra tree depth to find more signal. This is the direct evidence for Task 3's model-choice question — a larger model (e.g. a neural network) would have more capacity than this dataset can support, at a real cost to interpretability, for no measurable accuracy gain.

## Slice Evaluation (by `loyalty_tier`)

| Tier | n | positives | AUC | Recall@10% | Too small to conclude? | Flagged (recall ≥10pp below aggregate) |
|---|---|---|---|---|---|---|
| Bronze | 1,071 | 361 | 0.7509 | 0.4377 | No | No |
| Silver | 1,139 | 226 | 0.7107 | 0.2080 | No | **Yes** |
| Gold | 483 | 52 | 0.7364 | 0.1346 | No | **Yes** |
| Platinum | 307 | 21 | 0.8631 | 0.0952 | No | **Yes** |

All four tiers clear the size floor (n≥30, positives≥10) used here to call a slice statistically usable — Platinum is the smallest at 21 positives, which is still enough to report but is the tier where a single flipped prediction moves the recall number the most, so its recall figure should be read with more caution than the others.

**Weakest tier, by AUC:** Silver (0.7107) — the model discriminates churners from non-churners least well within this tier.

**Weakest tier, by recall@10%:** Platinum (0.0952) — despite having the *highest* AUC of any tier (0.8631), almost none of Platinum's churners land in the global top-10%-by-risk bucket that `precision_top10`/`recall_top10` are computed against. This is not a contradiction: recall@10% here uses one global threshold across all customers, not a per-tier one, so it measures "would this customer be in the overall outreach list," not "does the model separate churners within this tier." Platinum customers tend to score lower in absolute risk than Bronze/Silver customers even when the model ranks them correctly relative to each other — so a high-AUC, low-recall@10% tier means the model understands Platinum churn risk well, but Platinum rarely rises to the top of a company-wide priority list under a flat 10% contact budget. Whether that's the right business behavior (expensive-to-retain Platinum customers should perhaps get a dedicated, lower threshold) is a design question, not a model-quality one.

Silver and Gold are flagged for the same underlying reason as Platinum: tier-relative risk doesn't translate directly into cross-tier rank under one shared threshold. Bronze is unflagged and has the strongest recall (0.4377) — the bulk of its customers who churn score consistently near the top of the global distribution.

## Evidence

- `docs/lab3-evidence/train-final.log` — console output of the graded run, including `Athena QueryExecutionId`.
- `docs/lab3-evidence/evaluation_metrics.json` — metrics from the graded run.
- `docs/lab3-evidence/slice-evaluation.csv` — raw slice table above.
- `docs/lab3-evidence/confusion-matrix.png` — confusion matrix at threshold 0.5.
- `docs/lab3-evidence/feature-importance.png` — gain-based feature importance.
- MLflow App `northstar-mlflow` (ARN `arn:aws:sagemaker:us-east-1:761641207876:mlflow-app/app-DSCTLP23JOQQ`), experiment `northstar-churn`.
- Model Registry: `northstar-churn-models`, `PendingManualApproval` (not yet approved, per requirement).
