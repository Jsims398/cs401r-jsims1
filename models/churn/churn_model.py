"""Your Lab 3 churn model, packaged for the Lab 4 pipeline.

YOU WRITE THIS FILE. The pipeline's training job runs train_sagemaker.py
(beside this file; do not edit it), which imports this module and calls
train(). Everything the job needs from you goes through the three names below.

Contract (train_sagemaker.py checks it in the first seconds of the job):

    FEATURE_COLUMNS   list[str]   model input columns, in order
    LABEL             str         "churn_label"
    train(df, seed=42) -> (xgboost.Booster, dict)

`df` is the full labeled feature table: every column of your Lab 2 output,
including `loyalty_tier` for slice evaluation. It is already loaded. Do not
query Athena or the Feature Store from here; the training container stages
the data for you and has no business making service calls for its input.

The metrics dict must include the four numbers the CI gate in
tests/test_model.py reads. Your Lab 3 evaluate_model() already returns them:

    precision_top10, recall_top10      gated at 0.50 / 0.25
    lift_ci_low, lift_ci_high          bootstrap 95% CI on AUC lift over the
                                       recency-only baseline; lift_ci_low > 0

Include anything else you reported in Lab 3 (auc_roc, baseline_auc,
positive_rate_val, slice results). It is all written to evaluation_metrics.json
and attached to the registered model.

What runs in the container: the SageMaker XGBoost 1.7-1 image ships pandas,
numpy, scikit-learn, xgboost and boto3. It does NOT ship mlflow or sagemaker,
so do not import them at the top of this file. MLflow tracking stays in your
Lab 3 script.

Only this directory (models/churn/) is uploaded to the training job, so the
code must live here. `import churn_training_skeleton` will fail inside the
container even though it works on your laptop. Copy the functions you need.

Test it locally before pushing:

    python models/churn/train_sagemaker.py \
        --train-channel <dir containing your features CSV or Parquet> \
        --model-dir /tmp/model --output-data-dir /tmp/out
"""


# Keeps Lab 3 annotations like `-> tuple[np.ndarray, np.ndarray]` from being
# evaluated, whatever Python the training container runs.
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

# Must match the columns your Lab 3 model was trained on, in the same order.
# churn_label (target), customer_id (identifier), loyalty_tier (slice column,
# correlates with spend) and churn_risk_score (the recency heuristic) stay out.
FEATURE_COLUMNS = [
    "days_since_last_purchase",
    "customer_tenure_days",
    "purchase_frequency_30d",
    "purchase_frequency_90d",
    "purchase_frequency_180d",
    "avg_order_value",
    "total_spend_90d",
    "total_lifetime_value",
    "avg_basket_size_6m",
    "category_diversity_score",
    "online_to_store_ratio",
]

LABEL = "churn_label"
SLICE_COLUMN = "loyalty_tier"
BASELINE_FEATURE = "days_since_last_purchase"

# Lab 3 parse_args() defaults. scale_pos_weight=None means "compute from the
# training split" (lands near 3.5 on the reference data).
HYPERPARAMS = {
    "max_depth": 6,
    "eta": 0.1,
    "num_round": 200,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "scale_pos_weight": None,
}

EVAL_THRESHOLDS = {
    "precision_top10": 0.50,   # Minimum precision @ top 10% scored customers
    "recall_top10":    0.25,   # Minimum recall @ top 10% scored customers
}
# No absolute AUC threshold (removed 2026-08-02: the reference model fell below
# 0.72 on 58% of random splits). The baseline gate is the bootstrap lift CI.
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

# Slices below either floor are reported but flagged too small to conclude from.
MIN_SLICE_N = 30
MIN_SLICE_POSITIVES = 10


def preprocess_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """X, y arrays. The Lab 2 job asserts no nulls in any feature, so -1 is a
    defensive sentinel only; XGBoost would also accept NaN natively."""
    X = df[FEATURE_COLUMNS].astype(float).fillna(-1).to_numpy()
    y = df[LABEL].to_numpy().astype(int)
    print(f"  Positive class rate: {y.mean():.1%}")
    print(f"  Feature matrix shape: {X.shape}")
    return X, y


def train_model(X_train, y_train, X_val, y_val, seed: int = 42) -> tuple[xgb.Booster, dict]:
    """Train the XGBoost churn model. Returns (booster, resolved params)."""
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_COLUMNS)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)

    spw = HYPERPARAMS["scale_pos_weight"]
    if spw is None:
        spw = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))

    params = {
        # XGBoost early-stops on the LAST eval_metric. Keep "auc" last, or
        # reweighted logloss drives early stopping and AUC drops (defect 49).
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": HYPERPARAMS["max_depth"],
        "eta": HYPERPARAMS["eta"],
        "min_child_weight": HYPERPARAMS["min_child_weight"],
        "subsample": HYPERPARAMS["subsample"],
        "colsample_bytree": HYPERPARAMS["colsample_bytree"],
        "scale_pos_weight": spw,
        # More days dormant must never LOWER churn risk. Unconstrained, split
        # noise produced a 0.028 dip between 60 and 90 days, failing
        # tests/test_model.py::test_model_monotone_on_recency.
        "monotone_constraints": "(" + ",".join(
            "1" if c == BASELINE_FEATURE else "0" for c in FEATURE_COLUMNS) + ")",
        "seed": seed,
        "verbosity": 1,
    }
    print(f"\nTraining XGBoost with params: {json.dumps(params, indent=2)}")

    model = xgb.train(
        params=params,
        dtrain=dtrain,
        num_boost_round=HYPERPARAMS["num_round"],
        evals=[(dtrain, "train"), (dval, "validation")],
        early_stopping_rounds=20,
        verbose_eval=25,
    )
    return model, params


def train_recency_baseline(X_train, y_train, X_val) -> np.ndarray:
    """Model over days_since_last_purchase ALONE, same train/val rows as the
    full model. Not a constant predictor: the question is whether the feature
    set beats the rule the business already has for free."""
    i = FEATURE_COLUMNS.index(BASELINE_FEATURE)
    dtr = xgb.DMatrix(X_train[:, [i]], label=y_train, feature_names=[BASELINE_FEATURE])
    dva = xgb.DMatrix(X_val[:, [i]], feature_names=[BASELINE_FEATURE])
    spw = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    params = {
        "objective": "binary:logistic", "eval_metric": "auc",
        "max_depth": 4, "eta": 0.1, "subsample": 0.9,
        "colsample_bytree": 0.9, "scale_pos_weight": spw, "seed": 42,
    }
    return xgb.train(params, dtr, num_boost_round=200).predict(dva)


def bootstrap_lift_ci(y_true, proba, baseline_proba,
                      n: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED,
                      alpha: float = 0.05) -> tuple[float, float]:
    """Paired percentile CI for (model AUC - baseline AUC) over val resamples.
    Single-class replicates are skipped (AUC undefined)."""
    rng = np.random.default_rng(seed)
    y_true = np.asarray(y_true)
    idx = np.arange(len(y_true))
    diffs = []
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        ys = y_true[s]
        if len(np.unique(ys)) < 2:
            continue
        diffs.append(roc_auc_score(ys, proba[s]) - roc_auc_score(ys, baseline_proba[s]))
    if len(diffs) < n // 2:
        raise ValueError(
            "Too few usable bootstrap replicates to form a confidence interval. "
            "Your validation set is too small or too imbalanced to support this gate."
        )
    d = np.sort(diffs)
    return float(np.quantile(d, alpha / 2)), float(np.quantile(d, 1 - alpha / 2))


def evaluate_model(model: xgb.Booster, X_val, y_val, baseline_proba) -> dict:
    """Metrics dict. Raises ValueError if any gate fails, so a model that misses
    a gate fails the training step and is never registered."""
    y_pred_proba = model.predict(xgb.DMatrix(X_val, feature_names=FEATURE_COLUMNS))

    auc_roc = roc_auc_score(y_val, y_pred_proba)

    top10_threshold = np.percentile(y_pred_proba, 90)
    top10_mask = y_pred_proba >= top10_threshold
    precision_top10 = y_val[top10_mask].mean() if top10_mask.sum() > 0 else 0.0
    recall_top10 = y_val[top10_mask].sum() / y_val.sum() if y_val.sum() > 0 else 0.0

    baseline_auc = roc_auc_score(y_val, baseline_proba)
    lift_ci_low, lift_ci_high = bootstrap_lift_ci(y_val, y_pred_proba, baseline_proba)

    metrics = {
        "auc_roc": round(float(auc_roc), 4),
        "precision_top10": round(float(precision_top10), 4),
        "recall_top10": round(float(recall_top10), 4),
        "auc_vs_baseline": round(float(auc_roc - baseline_auc), 4),
        "baseline_auc": round(float(baseline_auc), 4),
        "lift_ci_low": round(float(lift_ci_low), 4),
        "lift_ci_high": round(float(lift_ci_high), 4),
        "positive_rate_val": round(float(y_val.mean()), 4),
        "n_val_samples": int(len(y_val)),
        "eval_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print("\n── Evaluation Results ──────────────────────────────")
    failures = []
    for metric, threshold in EVAL_THRESHOLDS.items():
        value = metrics[metric]
        status = "PASS" if value >= threshold else "FAIL"
        print(f"  {metric:25s}: {value:.4f}  (threshold: {threshold:.4f})  {status}")
        if value < threshold:
            failures.append(f"{metric}={value:.4f} < {threshold}")

    ci_status = "PASS" if lift_ci_low > 0 else "FAIL"
    print(f"  {'auc_lift 95% CI':25s}: [{lift_ci_low:.4f}, {lift_ci_high:.4f}]"
          f"  (must exclude 0)  {ci_status}")
    if lift_ci_low <= 0:
        failures.append(
            f"auc_lift 95% CI [{lift_ci_low:.4f}, {lift_ci_high:.4f}] includes "
            f"zero - no evidence the model beats the recency-only baseline")

    if failures:
        raise ValueError(
            f"Model failed evaluation thresholds: {'; '.join(failures)}. "
            f"Do not promote to Model Registry."
        )
    print("  All thresholds passed")
    return metrics


def evaluate_slices(model: xgb.Booster, X_val, y_val, slice_column: pd.Series,
                    aggregate_recall: float) -> dict:
    """Per-tier AUC and recall@10%, using the SAME global top-10% threshold as
    evaluate_model(), so "contact budget" means the same thing in every tier."""
    y_pred_proba = model.predict(xgb.DMatrix(X_val, feature_names=FEATURE_COLUMNS))
    top10_threshold = np.percentile(y_pred_proba, 90)
    slice_values = np.asarray(slice_column, dtype=object)

    slice_results = {}
    for slice_value in pd.unique(slice_values):
        mask = slice_values == slice_value
        y_slice = y_val[mask]
        proba_slice = y_pred_proba[mask]

        n = int(mask.sum())
        positives = int(y_slice.sum())
        too_small = n < MIN_SLICE_N or positives < MIN_SLICE_POSITIVES

        auc_slice = (float(roc_auc_score(y_slice, proba_slice))
                     if len(np.unique(y_slice)) > 1 else None)
        recall_slice = (float(y_slice[proba_slice >= top10_threshold].sum() / positives)
                        if positives > 0 else None)
        recall_flagged = (not too_small and recall_slice is not None
                          and aggregate_recall - recall_slice > 0.10)

        slice_results[str(slice_value)] = {
            "tier": str(slice_value),
            "n": n,
            "positives": positives,
            "auc": round(auc_slice, 4) if auc_slice is not None else None,
            "recall_top10": round(recall_slice, 4) if recall_slice is not None else None,
            "too_small_to_conclude": too_small,
            "recall_flagged_vs_aggregate": bool(recall_flagged),
        }

    print("\n── Slice Evaluation (by loyalty_tier) ──────────────────────")
    for tier, r in slice_results.items():
        flag = " [TOO SMALL]" if r["too_small_to_conclude"] else ""
        flag += " [RECALL DROP]" if r["recall_flagged_vs_aggregate"] else ""
        print(f"  {tier:10s} n={r['n']:4d}  positives={r['positives']:3d}  "
              f"auc={r['auc']}  recall@10%={r['recall_top10']}{flag}")
    return slice_results


def train(df: pd.DataFrame, seed: int = 42):
    """Train the churn model on `df` and return (booster, metrics)."""
    # Drop unlabeled rows BEFORE extracting X so X, y and tiers stay aligned.
    df = df.dropna(subset=[LABEL]).reset_index(drop=True)
    print(f"Preprocessing {len(df):,} samples...")
    X, y = preprocess_features(df)

    # tier rides along on the identical split indices. A Series, not .values
    # (an Arrow array under pandas 3 that train_test_split cannot index).
    X_train, X_val, y_train, y_val, tier_train, tier_val = train_test_split(
        X, y, df[SLICE_COLUMN], test_size=0.30, random_state=seed, stratify=y
    )
    print(f"\nTrain: {len(X_train):,} | Validation: {len(X_val):,}")

    model, params = train_model(X_train, y_train, X_val, y_val, seed=seed)

    baseline_proba = train_recency_baseline(X_train, y_train, X_val)
    metrics = evaluate_model(model, X_val, y_val, baseline_proba)

    slices = evaluate_slices(model, X_val, y_val, tier_val, metrics["recall_top10"])
    metrics["slice_results"] = slices
    metrics["best_iteration"] = int(model.best_iteration)
    metrics["scale_pos_weight"] = round(float(params["scale_pos_weight"]), 4)
    metrics["n_train_samples"] = int(len(y_train))

    return model, metrics
