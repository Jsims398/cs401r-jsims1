"""
Pandas port of the Lab 2 feature logic (glue-scripts/feature_engineer.py).

Same definitions as the Glue job, so the CI tests gate the logic the model
actually trains on:
  * every window is measured backwards from snapshot_date (the Glue job's
    FEATURE_CUTOFF), never from today()
  * only purchases on or before snapshot_date count
  * "within N days" means datediff(T, purchase_date) <= N, as in F.datediff
  * avg_basket_size_6m is ITEMS per order over the last 180 days, not dollars

Null strategy: a customer on the roster with no purchases in the observation
window gets NO_PURCHASE_RECENCY for days_since_last_purchase and 0 for every
count, sum, ratio and tenure. Customers with at least one purchase never
produce a NaN.
"""

import pandas as pd

N_CATEGORIES = 8.0
NO_PURCHASE_RECENCY = 999

# Loyalty tier thresholds on total lifetime value (USD), same as the Glue job.
TIER_BRONZE_MAX = 500.0
TIER_SILVER_MAX = 2000.0
TIER_GOLD_MAX = 5000.0

RECENCY_COLS = ["days_since_last_purchase", "customer_tenure_days"]
FREQUENCY_COLS = ["purchase_frequency_30d", "purchase_frequency_90d", "purchase_frequency_180d"]
MONETARY_COLS = ["avg_order_value", "total_spend_90d", "total_lifetime_value", "avg_basket_size_6m"]
BEHAVIORAL_COLS = ["category_diversity_score", "online_to_store_ratio"]


def _history(transactions, snapshot_date):
    """Transactions on or before T, with a whole-day `_days_ago` column."""
    T = pd.Timestamp(snapshot_date).normalize()
    df = transactions.copy()
    df["purchase_date"] = pd.to_datetime(df["purchase_date"]).dt.normalize()
    df = df[df["purchase_date"] <= T]
    df["_days_ago"] = (T - df["purchase_date"]).dt.days
    return df


def _reindex(features, customer_ids, fill):
    """Left-join onto the roster so customers with no purchases still get a row."""
    if customer_ids is None:
        return features
    roster = customer_ids[["customer_id"]].drop_duplicates()
    out = roster.merge(features, on="customer_id", how="left")
    return out.fillna(fill)


def compute_recency_features(transactions, snapshot_date, customer_ids=None):
    """days_since_last_purchase and customer_tenure_days, in days before T."""
    df = _history(transactions, snapshot_date)
    g = df.groupby("customer_id")["_days_ago"]
    features = pd.DataFrame({
        "days_since_last_purchase": g.min(),
        "customer_tenure_days": g.max(),
    }).reset_index()
    features = _reindex(features, customer_ids,
                        {"days_since_last_purchase": NO_PURCHASE_RECENCY, "customer_tenure_days": 0})
    return features.astype({c: float for c in RECENCY_COLS})


def compute_frequency_features(transactions, snapshot_date, customer_ids=None):
    """Order counts in the 30/90/180 days before T."""
    df = _history(transactions, snapshot_date)
    for n in (30, 90, 180):
        df[f"purchase_frequency_{n}d"] = (df["_days_ago"] <= n).astype(int)
    features = df.groupby("customer_id")[FREQUENCY_COLS].sum().reset_index()
    features = _reindex(features, customer_ids, 0)
    return features.astype({c: float for c in FREQUENCY_COLS})


def compute_monetary_features(transactions, snapshot_date, customer_ids=None):
    """avg_order_value, total_spend_90d, total_lifetime_value, avg_basket_size_6m."""
    df = _history(transactions, snapshot_date)
    in_90 = df["_days_ago"] <= 90
    in_180 = df["_days_ago"] <= 180
    df["_spend_90d"] = df["order_value"].where(in_90, 0.0)
    df["_items_6m"] = df["num_items"].where(in_180, 0)
    df["_orders_6m"] = in_180.astype(int)

    g = df.groupby("customer_id")
    features = pd.DataFrame({
        "avg_order_value": g["order_value"].mean(),
        "total_spend_90d": g["_spend_90d"].sum(),
        "total_lifetime_value": g["order_value"].sum(),
        "_items_6m": g["_items_6m"].sum(),
        "_orders_6m": g["_orders_6m"].sum(),
    }).reset_index()
    # Guarded denominator: no orders in the last 180 days -> 0.0, as in Glue.
    orders = features["_orders_6m"]
    features["avg_basket_size_6m"] = (features["_items_6m"] / orders.where(orders > 0)).fillna(0.0)
    features = features[["customer_id"] + MONETARY_COLS]
    features = _reindex(features, customer_ids, 0.0)
    return features.astype({c: float for c in MONETARY_COLS})


def compute_behavioral_features(transactions, snapshot_date=None, customer_ids=None):
    """category_diversity_score (distinct real categories / 8) and online_to_store_ratio
    (fraction of orders placed online). Over the whole observation window."""
    df = transactions if snapshot_date is None else _history(transactions, snapshot_date)
    df = df.copy()
    # The transform imputes 'unknown' for missing categories; it is not a real category.
    df["_category"] = df["product_category"].where(df["product_category"] != "unknown")
    df["_online"] = (df["channel"] == "online").astype(int)

    g = df.groupby("customer_id")
    features = pd.DataFrame({
        "category_diversity_score": g["_category"].nunique() / N_CATEGORIES,
        "online_to_store_ratio": g["_online"].mean(),
    }).reset_index()
    features = _reindex(features, customer_ids, 0.0)
    return features.astype({c: float for c in BEHAVIORAL_COLS})


def assign_loyalty_tier(total_lifetime_value):
    """Bronze < 500 <= Silver < 2000 <= Gold < 5000 <= Platinum."""
    return pd.cut(
        total_lifetime_value,
        bins=[-float("inf"), TIER_BRONZE_MAX, TIER_SILVER_MAX, TIER_GOLD_MAX, float("inf")],
        labels=["Bronze", "Silver", "Gold", "Platinum"],
        right=False,
    ).astype(str)


def build_churn_feature_set(customers, transactions, snapshot_date):
    """One row per customer on the roster with every model feature.

    Keeps the roster's own columns (loyalty_tier, churn_label, ...) and fills
    loyalty_tier from lifetime value only where the roster does not carry it.
    """
    ids = customers[["customer_id"]]
    features = customers.copy()
    for part in (
        compute_recency_features(transactions, snapshot_date, ids),
        compute_frequency_features(transactions, snapshot_date, ids),
        compute_monetary_features(transactions, snapshot_date, ids),
        compute_behavioral_features(transactions, snapshot_date, ids),
    ):
        features = features.merge(part, on="customer_id", how="left")
    if "loyalty_tier" not in features.columns:
        features["loyalty_tier"] = assign_loyalty_tier(features["total_lifetime_value"])
    return features
