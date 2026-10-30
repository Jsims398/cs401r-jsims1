"""
NorthStar Retail — Fairness (slice) Tests
CS 401R Lab 4, Task 1

Manual slice evaluation of the churn model by loyalty_tier. Reads the
evaluation_metrics.json the training run emitted (EVAL_METRICS_PATH, the same
file tests/test_model.py gates on); churn_model.train() writes the per-tier
results into it under "slice_results".

Policy: a recall@10% gap of more than 10 percentage points between the highest-
and lowest-recall tier is FLAGGED, not blocked. The flag is a pytest warning,
so it shows in the build's warnings summary (buildspec runs pytest with -rw)
where the approver sees it before approving the package. Missing or malformed
slice results are a FAILURE: a fairness check that cannot see the slices has
checked nothing.

Run locally:
    pytest tests/test_fairness.py -v -rw --eval-metrics-path /tmp/out/evaluation_metrics.json
"""

import json
import os
import warnings

import pytest

VALID_TIERS = {"Bronze", "Silver", "Gold", "Platinum"}
MAX_RECALL_GAP = 0.10


class FairnessWarning(UserWarning):
    """Recall differs across loyalty tiers by more than the policy allows."""


@pytest.fixture(scope="module")
def eval_metrics():
    path = os.environ.get("EVAL_METRICS_PATH", "/tmp/eval_metrics.json")
    if not os.path.exists(path):
        pytest.fail(f"Evaluation metrics not found at {path}. Set EVAL_METRICS_PATH "
                    f"or pass --eval-metrics-path.", pytrace=False)
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def slices(eval_metrics):
    s = eval_metrics.get("slice_results")
    if not s:
        pytest.fail("evaluation_metrics.json has no slice_results. "
                    "churn_model.train() must include the per-tier breakdown.",
                    pytrace=False)
    return s


def test_every_tier_evaluated(slices):
    missing = VALID_TIERS - set(slices)
    assert not missing, f"No slice results for tiers: {sorted(missing)}"


def test_slice_counts_consistent(eval_metrics, slices):
    """Slices partition the validation set: sizes sum to n_val_samples and each
    tier has at least one churner, so recall is defined everywhere."""
    total = sum(r["n"] for r in slices.values())
    assert total == eval_metrics["n_val_samples"], (
        f"Slice sizes sum to {total}, validation set has {eval_metrics['n_val_samples']}"
    )
    no_positives = [t for t, r in slices.items() if not r["positives"]]
    assert not no_positives, f"Tiers with no churners (recall undefined): {no_positives}"


def test_slice_metrics_in_range(slices):
    for tier, r in slices.items():
        assert 0.0 <= r["recall_top10"] <= 1.0, f"{tier} recall_top10 out of [0, 1]"
        if r["auc"] is not None:
            assert 0.0 <= r["auc"] <= 1.0, f"{tier} auc out of [0, 1]"


def test_recall_gap_across_tiers(slices):
    """Flag (do not fail) when the highest- and lowest-recall tiers differ by
    more than 10pp. Tiers below the sample-size floor are named in the warning
    so the approver can weigh how much the gap rests on a handful of churners."""
    recalls = {t: r["recall_top10"] for t, r in slices.items()}
    hi = max(recalls, key=recalls.get)
    lo = min(recalls, key=recalls.get)
    gap = recalls[hi] - recalls[lo]

    if gap > MAX_RECALL_GAP:
        small = [t for t, r in slices.items() if r["too_small_to_conclude"]]
        detail = ", ".join(f"{t}={recalls[t]:.3f} (n={slices[t]['n']}, "
                           f"positives={slices[t]['positives']})"
                           for t in sorted(recalls, key=recalls.get, reverse=True))
        warnings.warn(
            f"FAIRNESS FLAG: recall@10% gap {gap:.3f} between {hi} and {lo} "
            f"exceeds {MAX_RECALL_GAP:.2f}. Per tier: {detail}."
            + (f" Too small to conclude from: {small}." if small else ""),
            FairnessWarning,
        )
