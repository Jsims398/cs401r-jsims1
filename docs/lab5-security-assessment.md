# NorthStar Churn Model - Security and Privacy Assessment

Scope: the churn prediction system as deployed in Lab 5. That covers the data bucket `northstar-dev-data-<account>` (`raw/`, `processed/`, `features/`, `artifacts/`, `datacapture/`), the Glue jobs, the Feature Store group `northstar-dev-customer-features`, the SageMaker training pipeline and Model Registry, and the real-time endpoint `northstar-churn-prod`.

The existing least-privilege boundary is the three roles from Lab 2 (`infrastructure/modules/iam/main.tf`):

| Role | Can do | Cannot do |
| --- | --- | --- |
| MLEngineer | SageMaker training and serving; S3 get/put/delete on `artifacts/*` and `features/*`; put on `datacapture/*` | Touch `raw/` or `processed/`, or use Glue or Athena |
| DataEngineer | Glue (`glue:*` on `*`); S3 on `raw/`, `processed/` and `features/`; read `artifacts/glue/*`; Feature Store | Write model artifacts, or call the endpoint |
| ModelMonitor | CloudWatch metrics; SageMaker read-only; read `artifacts/*` | Write anything to S3, or change endpoints |

## 3a. STRIDE threat model

| # | Threat | STRIDE category | Likelihood | Impact | Mitigation | AWS control |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A leaked long-lived access key for the `cs401r-lab` IAM user is used to call `InvokeEndpoint`, `DeleteEndpoint` or `UpdateModelPackage`, posing as the ML team | Spoofing | Medium | High | Replace user access keys with short-lived role sessions behind MFA; block committed keys in CI; alert on API calls from unexpected IP addresses or regions | **IAM Identity Center** or `sts:AssumeRole` with an `aws:MultiFactorAuthPresent` condition; `scripts/check-secrets.sh` in CodeBuild; **GuardDuty** `UnauthorizedAccess:IAMUser/*` findings |
| 2 | Someone replaces `model.tar.gz` under `artifacts/training/` with a tampered booster, for example one that scores a chosen segment as low risk so those customers never get offers, and the next deployment serves it | Tampering | Low | High | **Blast radius contained by the MLEngineer role:** only MLEngineer can `PutObject` or `DeleteObject` under `artifacts/*`. DataEngineer can only read `artifacts/glue/*`, and ModelMonitor is read-only. Also: version the bucket, verify the artifact against the registry's ETag before `create-model`, and require approval in the Model Registry before deployment | **S3 Versioning** (enabled) plus **S3 Object Lock** (governance mode) on `artifacts/training/`; **SageMaker Model Registry** `ModelDataETag` and `ModelApprovalStatus`; **IAM** prefix-scoped `s3:PutObject` |
| 3 | An approver later denies having approved v8 or v9, or a canary is promoted with no record of who did it | Repudiation | Medium | Medium | Record every approval and endpoint change with the caller's identity; keep an approval note on the package | **CloudTrail** management events for `UpdateModelPackage`, `UpdateEndpointWeightsAndCapacities` and `CreateEndpoint`, sent to a log bucket with **CloudTrail log file validation**; **Model Registry** `ApprovalDescription` and `LastModifiedBy` |
| 4 | Membership or attribute inference: a caller sends many crafted feature vectors to the endpoint and uses the returned probabilities to learn whether a particular customer was in the training data | Information Disclosure | Medium | High | Limit who can invoke the endpoint; return a risk band rather than a raw probability to non-ML callers; rate-limit callers | **IAM** `sagemaker:InvokeEndpoint` granted only to the offer-system role; **API Gateway** usage plans or **AWS WAF** rate rules in front of the endpoint; **CloudWatch** `Invocations` anomaly detection |
| 5 | Captured inference payloads in `datacapture/` (the full feature vector and score for every request) are read by anyone with bucket read access. Data capture is a new copy of customer behavioural data that sits outside the Feature Store's access controls | Information Disclosure | Medium | High | **Gap the three roles do not close:** the roles limit what the *pipeline principals* can do, but human IAM users with broad S3 access (the lab user, any `AmazonS3ReadOnlyAccess` holder) can read `datacapture/` with no role boundary. The bucket uses SSE-S3, so S3 read permission is enough to decrypt. Fix: a bucket policy that denies `datacapture/*` reads to everyone except ModelMonitor, plus SSE-KMS with a key whose policy names only that role | **S3 bucket policy** with an `aws:PrincipalArn` deny; **SSE-KMS** customer managed key with a key policy restricted to ModelMonitor; **lifecycle rule** `expire-datacapture` (7 days, then noncurrent versions deleted after 1 day) |
| 6 | Someone floods the endpoint with invocations, so auto-scaling adds instances and the bill grows, or latency rises past the offer system's 2-second budget | Denial of Service | Medium | Medium | Cap the scaling ceiling; throttle at the edge; alert on spend | **Application Auto Scaling** `MaxCapacity: 2` (`deployment/configs/scalable-target.json`); **AWS WAF** rate-based rule or **API Gateway** throttling; **AWS Budgets** alert; rollback alarm `northstar-churn-rollback-canary-latency` |
| 7 | A compromised Glue job or DataEngineer session uses `glue:*` on `*` to rewrite another job's script location, or to create a Glue connection into the private subnet and run arbitrary code with the role's S3 and Feature Store access | Elevation of Privilege | Low | High | **Gap in the roles:** DataEngineer's `GlueFullAccess` statement and its Feature Store statement are both `Resource = "*"`. Scope Glue actions to `arn:aws:glue:*:*:job/northstar-dev-*` and the `northstar_dev` catalog, and drop `glue:CreateConnection` | **IAM** resource-scoped policies; **IAM Access Analyzer** policy validation and unused-access findings; **CloudTrail** alert on `glue:UpdateJob` |

Coverage: Spoofing (1), Tampering (2), Repudiation (3), Information Disclosure (4, 5), Denial of Service (6), Elevation of Privilege (7). Row 2 shows a Lab 2 role containing the blast radius; rows 5 and 7 are gaps those roles do not close.

## 3b. Data classification

Encryption choices:
- **SSE-S3** (AES256, which is what the bucket uses today) encrypts at rest, but anyone allowed `s3:GetObject` can read the data, and decryption is not logged separately.
- **SSE-KMS** adds a second check (the key policy must also allow `kms:Decrypt`), logs every decrypt in CloudTrail, and supports crypto-shredding by disabling or deleting the key.
- **CSE** (client-side encryption) means AWS never sees plaintext. That would break Glue and SageMaker processing, so it is reserved for data that no AWS service needs to read.

| Asset | Where it lives | Tier | Encryption | IAM access policy | Share with a third-party vendor? |
| --- | --- | --- | --- | --- | --- |
| Customer PII (`customer_id`, hashed email, age band, state, zip) | CRM export into `raw/` | **Restricted** | **SSE-KMS** with a dedicated key. Direct identifiers and quasi-identifiers (zip plus age band) can re-identify a person, so decryption needs its own audit trail and erasure needs a crypto-shred option | DataEngineer read/write `raw/`; nobody else. Key policy: DataEngineer and the Glue service only | **No.** Only pseudonymised extracts, under a GDPR Art. 28 processor agreement, approved by the Chief Privacy Officer |
| Transaction history (amounts, dates, store, payment method) | `raw/`, `processed/` | **Confidential** | **SSE-KMS**. It is linked to `customer_id` and reveals spending behaviour, so access must be audited per decrypt | DataEngineer read/write; MLEngineer has no access to `raw/` or `processed/` | Aggregates only (for example category totals with no `customer_id`) |
| Behavioural clickstream (sessions, product views, search queries) | `raw/` (when ingested) | **Restricted** | **SSE-KMS**. The schema warns that `search_query` sometimes contains typed email addresses, so it is unvetted free-text PII | DataEngineer only; scrub `search_query` before anything reaches `processed/` | **No** |
| Product catalog | `raw/` reference data | **Internal** | **SSE-S3**. No personal data; it is commercially sensitive before launch but not regulated, so KMS's audit cost buys nothing | Read for all three roles | **Yes**, with prices and margins removed |
| Model weights (`artifacts/training/*/model.tar.gz`) | `artifacts/` | **Confidential** | **SSE-KMS**. The model is NorthStar's IP, can memorise training records (threat 4), and tampering with it is threat 2, so reads and writes should be audited | MLEngineer read/write; ModelMonitor read; DataEngineer none | **No** |
| Inference logs (`datacapture/` jsonl: feature vector and score per request) | `datacapture/` | **Restricted** | **SSE-KMS** with a key restricted to ModelMonitor (threat 5). Each record joins customer behaviour to a churn prediction about a person | MLEngineer put only (the endpoint writes as that role); ModelMonitor read; humans denied by bucket policy | **No** |
| Feature Store records (16 features per `customer_id`, including `loyalty_tier` and `churn_label`) | Online store, plus offline store under `features/` | **Confidential** | **SSE-KMS** for both the online store and the offline store (`OnlineStoreSecurityConfig` and `OfflineStoreConfig.S3StorageConfig.KmsKeyId`). These are derived personal data keyed by `customer_id` | DataEngineer write; MLEngineer read `features/*`; ModelMonitor none | **No** |

The bucket currently has a single SSE-S3 configuration (`infrastructure/modules/storage/main.tf`). Every SSE-KMS entry above is therefore a required change before real customer data arrives, not a description of the current setup.

## 4. Privacy impact assessment

### 4.1 Personal data inventory

| Pipeline stage | Location | Personal data processed |
| --- | --- | --- |
| Ingest | `raw/customers/` | `customer_id`, transaction dates and amounts, `payment_method`, `channel`, `store_id`, product category; CRM attributes (hashed email, age band, state, zip, loyalty tier) |
| Transform (Glue) | `processed/customers/` | The same rows, typed, deduplicated and imputed |
| Feature engineering (Glue) | `features/customers/` and the Feature Store (online and offline) | 16 derived features per `customer_id`: recency, frequency, spend, tenure, basket size, category diversity, channel ratio, loyalty tier, churn label |
| Training (SageMaker) | Training channel copied from `features/`; `artifacts/training/` | 11 behavioural features plus the label, linked to `customer_id` in the channel. The trained model encodes statistical influence from every training row |
| Serving (endpoint) | Request payload in memory; `datacapture/` | One feature vector per request and the returned churn probability, stored as jsonl for 7 days |
| Activation | Retention campaign and offer system | Customer ID, risk score, offer decision |

### 4.2 Lawful basis

**Legitimate interests (GDPR Art. 6(1)(f)).** NorthStar has a genuine interest in keeping existing customers: churn costs about $128.5M a year, at roughly $340 per churned customer. Predicting churn from a customer's own purchase history with NorthStar is processing that loyalty-program members would reasonably expect, it uses no special-category data, and the outcome is a retention offer, not a decision with legal or similarly significant effect.

The balancing test passes with safeguards in place: the minimised feature set (4.3), 7-day retention for inference logs, an opt-out from profiling-based marketing honoured from CRM contact preferences, and a privacy notice that names churn modelling.

- **Contractual necessity** does not fit. NorthStar can fulfil a purchase or the loyalty contract without predicting churn.
- **Consent** is the wrong tool. Making the model depend on opt-in would bias the training population, and withdrawal would force retraining. Consent remains the right basis for the marketing email itself, but not for the analytics behind it.

### 4.3 Data minimisation

The model uses 11 behavioural features (`FEATURE_COLUMNS` in `models/churn/churn_model.py`). The following were considered and **excluded**:

- **Email (even hashed), zip code and state.** Not predictive enough to justify the re-identification risk; location also acts as a proxy for protected characteristics.
- **Age band.** A protected characteristic, missing for about 8% of customers, and a fairness risk for the offer system's FCRA/ECOA obligations.
- **`payment_method` and `store_id` at row level.** Collapsed into `online_to_store_ratio`; raw payment type adds sensitivity without adding signal.
- **Clickstream `search_query`.** Free text that may contain email addresses; not ingested.
- **`loyalty_points` balance and `loyalty_tier`.** Excluded as model inputs. `loyalty_tier` is kept in the Feature Store only for slice and fairness evaluation.
- **`churn_risk_score` (Feature Store).** Excluded as an input; it is a prior score and would leak the label.

### 4.4 Right to erasure: `customer_id = C00123456`

Before starting, confirm the request comes from the data subject (CRM identity check), log it in the DSAR tracker, and set the deadline to one month after receipt.

**(a) Raw S3 data.**
1. List the objects under `raw/` and `processed/` that contain the ID, for example with an Athena query on `northstar_dev` (`SELECT "$path" FROM ... WHERE customer_id = 'C00123456'`) or with S3 Select.
2. Rewrite each affected object without the customer's rows and upload it as a new version.
3. Because the bucket is **versioned**, the old versions still contain the data. Delete those versions explicitly with `aws s3api delete-object --version-id ...`, or let `expire-raw-versions` and `expire-processed-versions` remove them after 30 days and record that window in the response.

**(b) Feature Store.**
- **Online store:** `aws sagemaker-featurestore-runtime delete-record --feature-group-name northstar-dev-customer-features --record-identifier-value-as-string C00123456 --event-time <now> --deletion-mode HardDelete`. The record is removed from the low-latency store immediately.
- **Offline store:** `DeleteRecord` does **not** remove anything here. The offline store is append-only Parquet under `features/`, and a delete only appends a tombstone row with `is_deleted = true`, so every earlier row for C00123456 is still there. Rewrite the affected partitions without the customer, for example with Athena `CREATE TABLE AS SELECT ... WHERE customer_id <> 'C00123456'`, then copy the result back over those partitions. Then purge the noncurrent versions (`expire-feature-versions` would otherwise keep them for 60 days).

**(c) Model training data.** Remove the customer from the training snapshot, which happens automatically once (a) and (b) are complete. Then **retrain**: run `northstar-churn-pipeline`, approve the new package, deploy it with the canary process, set the old package to `Rejected`, and delete the old `model.tar.gz` and its versions from `artifacts/training/`.

**(d) Inference logs.** Search the `datacapture/` jsonl files for requests carrying this customer's feature vector. Captured payloads contain features, not `customer_id`, so the match has to come from the request ID in the offer system's logs. Rewrite or delete the matching files, or document that `expire-datacapture` hides them within 7 days and permanently deletes them a day later.

**Hardest step: (c), the trained model.** A trained XGBoost booster has no row-level delete. C00123456's data is not stored in the model as a record; it is spread across split thresholds and leaf weights. The only reliable way to erase it is to retrain without that customer and retire every model version trained with them, which costs a full training, approval and canary cycle. Approximate machine unlearning is not an established, auditable control.

The offline Feature Store is a close second for the same reason. "Delete" there is an append (a tombstone), so real erasure means rewriting history and purging object versions, not a single API call.
