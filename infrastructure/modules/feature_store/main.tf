# ── modules/feature_store ────────────────────────────────────────────────────
# One Feature Group: 16 definitions (2 keys, 13 features, 1 label). Online
# store enabled for real-time inference in Labs 3-4; offline store backed by
# features/offline-store/ in the data bucket, kept separate from the feature
# job's own features/customers/ output so the two don't interleave.
#
# event_time MUST be Fractional (Unix epoch seconds). Declaring it String and
# passing a numeric epoch — or the reverse — makes PutRecord return success
# while the record silently never appears in either store.

resource "aws_sagemaker_feature_group" "customer_features" {
  feature_group_name             = "${var.project}-${var.environment}-customer-features"
  record_identifier_feature_name = "customer_id"
  event_time_feature_name        = "event_time"
  role_arn                       = var.execution_role_arn

  feature_definition {
    feature_name = "customer_id"
    feature_type = "String"
  }
  feature_definition {
    feature_name = "event_time"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "days_since_last_purchase"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "customer_tenure_days"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "purchase_frequency_30d"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "purchase_frequency_90d"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "purchase_frequency_180d"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "avg_order_value"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "total_spend_90d"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "total_lifetime_value"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "avg_basket_size_6m"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "category_diversity_score"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "online_to_store_ratio"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "loyalty_tier"
    feature_type = "String"
  }
  feature_definition {
    feature_name = "churn_risk_score"
    feature_type = "Fractional"
  }
  feature_definition {
    feature_name = "churn_label"
    feature_type = "Integral"
  }

  online_store_config {
    enable_online_store = true
  }

  offline_store_config {
    s3_storage_config {
      s3_uri = "s3://${var.bucket_name}/features/offline-store/"
    }
  }

  tags = { Name = "${var.project}-${var.environment}-customer-features" }
}
