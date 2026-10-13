## Data Contract: processed/customers

### Producer
Team / process: Glue ETL job `northstar-dev-transform`. 

Reads the catalog table `northstar_dev.customers` (sourced from `raw/customers/`), casts types, imputes nulls, deduplicates on `transaction_id`, and writes to `processed/customers/`.

### Consumers
- Feature engineering job `northstar-dev-feature-engineer`
 - Reads this dataset to compute the 13 RFM/loyalty/churn-proxy features and the `churn_label`.
- (Future) Direct model training in Lab 3

### Grain
One row per transaction. A customer appears on many rows.

Filter for duplicate transactions not based on customer ID's. 

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `transaction_id` | string | No | `TXN-{12 alphanumeric}`. Natural key — one row per value after dedup. |
| `customer_id` | string | No | `CUST-{8 digits}`. Repeats across rows by design (transaction grain). |
| `purchase_date` | date | No | Parsed from ISO 8601 or `MM/DD/YYYY` source formats; both coalesced into a single `date` column. |
| `order_value` | double | No | USD, gross. Nulls imputed with the column median (not mean — the raw distribution is right-skewed). |
| `num_items` | int | No | Line items in the order. Nulls imputed with the rounded column median. |
| `payment_method` | string | No | `credit_card`, `debit_card`, `gift_card`, `cash`, or `unknown` (imputed). |
| `channel` | string | No | `store`, `online`, or `unknown` (imputed). |
| `store_id` | string | No | `STORE-{3 digits}`, `ONLINE`, or `unknown` (imputed). |
| `product_category` | string | No | Primary category for the order, or `unknown` (imputed). |

### Quality Guarantees

These are enforced by assertions in `northstar-dev-transform` itself — the
job fails rather than writing a dataset that violates them:

- `customer_id` is never null (rows with a null `customer_id` are dropped during `cast_types`, before any write).
- No duplicate `transaction_id` rows (`deduplicate` keeps exactly one row per `transaction_id`, most-recent by `purchase_date` on ties).
- `purchase_date` is always a valid, successfully parsed date — a row whose date matches neither `yyyy-MM-dd` nor `MM/dd/yyyy` would surface as a parse failure, not a silently null column.
- All columns are fully populated: numeric columns (`order_value`,
  `num_items`) are median-imputed, string columns (`payment_method`,
  `channel`, `store_id`, `product_category`) are imputed to `"unknown"` — there are no nulls anywhere in the output.
- Grain is preserved: this dataset is transaction-level, not customer-level. Row count exceeds distinct `customer_id` count. Collapsing to one row per customer here (instead of in the feature-engineering job) would make `total_lifetime_value` and `purchase_frequency_30d` impossible to compute downstream.

### SLA
`processed/customers/` is refreshed within 2 hours of a `raw/customers/` upload, given a manual `start-crawler` + `start-job-run` invocation. A future automated pipeline (Lambda-triggered on S3 `PutObject` to `raw/customers/`) would tighten this to near-real-time; that automation is out of scope for Lab 2.

### Versioning
- Schema changes (adding, removing, or retyping a column) require a new S3 prefix — e.g. `processed/customers/v2/` — rather than an in-place change to `processed/customers/`, so an in-flight consumer never reads a half-migrated dataset.
- Breaking changes (anything that changes a column's type or removes a column a consumer reads) require 5 business days' notice to the feature-engineering job's owner before the old prefix is deprecated.

