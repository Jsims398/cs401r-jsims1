# Lab 3 Walkthrough (personal notes)

Due Sat Oct 17, midnight. Source: Lab 3 handout + #lab3 Slack thread (Matthew King, Tom Esplín, Sara Hermosilla).

## 0. Before touching code

1. **Pre-Lab 3 Bedrock check** must already be passing (`docs/bedrock-access-verification.txt`). If not, do that first — Tracks B/C need it and a fix can take an AWS Support case.
2. **`terraform apply`** your infra stack. You cannot create the MLflow App without deployed infrastructure.
3. **Confirm the Lab 2 Feature Group is populated.** If you ever ran `teardown-lab2.sh` or `terraform destroy` since finishing Lab 2, assume it's empty — see §2.
4. Get the Lab 3 starter kit (Canvas or the [lab3 template repo](https://github.com/byu-cs401r4-f26/cs401r-lab3-template)) into this repo — do not start a new repo. Suggested placement (Matthew, 10/9):

| Starter file | Goes to |
|---|---|
| `churn_training_skeleton.py` | `models/churn/train.py` (or keep name) |
| `evaluation_harness.py` | `evaluation/evaluation_harness.py` |
| `prompt_templates/offer_generation_prompts.md` | `prompt_templates/offer_generation_prompts.md` |
| `northstar-policy-docs/` | `northstar-policy-docs/` |
| `scripts/teardown-lab3.sh` | `scripts/teardown-lab3.sh` |

RAG (Track B) has **no starter code** — make your own `rag/` folder for it.

Post questions in the Slack channel as you go, not just at blockers.

## 1. The data-loss trap (read this before any teardown)

This bit the team already once. Sequence of events:

- `terraform destroy` / the Lab 2 teardown **deletes the `northstar-dev-data` bucket contents and the Feature Group**, not just compute.
- `teardown-lab3.sh` does **not** cause this — it only touches Lab 3 resources (endpoints, jobs, the Track C agent stack) and deliberately **leaves the MLflow App alone**.
- `terraform apply` after a teardown recreates the resources **empty**. It does not restore data.
- A saved snapshot of `processed/` (the Glue job's S3 output) only saves you the ~15 min **transform job** time. It does **not** repopulate the **Feature Store / Athena offline store** — that still requires rerunning the feature-engineering Glue job. (Matthew's 8:25 PM correction superseded his earlier "just re-upload processed/" suggestion — don't follow the earlier one alone.)
- There is currently **no known way to snapshot/restore the Feature Store itself** (Tom asked directly; Matthew: "I haven't found a way to do so").

**Practical rule:** if the Lab 2 Feature Group / offline store needs to survive, the Lab 2 stack needs to stay deployed. Deleting the stack (via either teardown script or `terraform destroy`) loses it, full stop.

Optional time-saver if you *do* lose `processed/` only (not the Feature Group): keep a local snapshot of the processed Parquet output so re-running just the transform step is faster. It won't save you from needing to rerun the Glue job that populates the Feature Store.

## 2. Your workflow: phase 1 local, rest online, keep buckets up between phases

Given the plan to run Phase 1 (training script) locally first and do the rest against AWS, and to avoid repeatedly waiting on Glue + the pipeline:

- **Keeping the S3 bucket non-empty is not sufficient by itself** — see §1. What actually matters is **not tearing down the Lab 2 stack** between phases. As long as `terraform destroy`/`teardown-lab2.sh` is never run mid-lab, the Feature Group and offline store stay populated and every later phase can query Athena directly with no Glue rerun.
- Cost of leaving Lab 2 infra up: **up to ~$2/day** (Matthew, 8:48 PM). Given the lab window (through Oct 17), that's the right tradeoff versus re-running the Glue job (~15 min) repeatedly, and it's also what protects your trained models.
- **Models live in the artifact bucket, which is also deleted by a full Lab 2+3 teardown.** If you tear down between sessions, you lose trained models too and must retrain after `apply`. Staying up avoids that.
- Local Phase 1 work (testing `churn_training_skeleton.py` logic) can run against the Feature Store via Athena from your own machine under your own credentials — this is actually a **requirement**, not just a convenience: the lab requires the Athena query to run locally, not inside the training container (that role has no Athena/Glue permissions).
- Bottom line for your stated plan: **leave the Lab 2 stack (and the MLflow App) running for the whole lab**; only run `teardown-lab3.sh` for Lab-3-specific resources (endpoints, the Track C agent stack) when you're done testing something, not `teardown-lab2.sh` or a Lab 2 `terraform destroy`. Run the full Lab 2 teardown only once you are completely finished with Lab 3 and have already collected evidence and tagged your submission.

## 3. MLflow — the trap inside the trap

Two different AWS products, easy to confuse:

| | MLflow **App** (use this) | MLflow **Tracking Server** (do NOT use) |
|---|---|---|
| API | `CreateMlflowApp` | `CreateMlflowTrackingServer` |
| Cost | $0 | **$0.60/hr**, billed until deleted |
| Left running a weekend | $0 | **~$43** |

Most tutorials describe the Tracking Server since it shipped first — if you're asked to pick an instance size (Small/Medium), you're on the wrong product; the App is serverless with no size to pick.

Create once (~5 min to provision):
```bash
aws sagemaker create-mlflow-app \
  --name northstar-mlflow \
  --artifact-store-uri s3://northstar-dev-data-<account>/artifacts/mlflow/ \
  --role-arn arn:aws:iam::<account>:role/northstar-dev-MLEngineer \
  --query Arn --output text
```
Use the `MLEngineer` role / bucket from Lab 1 (`terraform output -raw ml_engineer_role_arn`, `terraform output -raw s3_bucket_name`) — don't create new ones. Needs a recent AWS CLI (`create-mlflow-app` postdates many installs — `Invalid choice` error means upgrade, not a typo). Needs both `mlflow` and `sagemaker-mlflow` packages installed.

Keep the App running after `teardown-lab3.sh` — it costs nothing and Labs 4/6 reuse it. The teardown script checks for a stray Tracking Server specifically (the expensive one) and will tell you if one exists; delete it immediately if so (`delete-mlflow-tracking-server` — stopping it is not enough, it can be restarted).

## 4. Task 1 (Track A, required) — checklist

Working file: `churn_training_skeleton.py` (wherever you place it per §0).

- [ ] Training data from Feature Store **offline store via Athena**, query run locally (not as `MLEngineer`), printing the `QueryExecutionId`.
- [ ] Add this block right before `# 2. Preprocess` / `X, y = preprocess_features(df)` (Matthew, 9:36 PM — not in the original skeleton):
  ```python
  # 1b. Drop rows with no label BEFORE extracting X, so df, X, y and tiers
  #     all have the same row order. preprocess_features() drops them too,
  #     but doing it there would misalign df[SLICE_COLUMN].
  df = df.dropna(subset=[LABEL_COLUMN]).reset_index(drop=True)
  ```
- [ ] XGBoost, hyperparameters passed as args (not hardcoded).
- [ ] Train locally first to iterate fast (fully supported path — no SageMaker Training Job required to pass). If using a real Training Job later, use **managed spot** (`use_spot_instances=True`, `max_wait=3600`) — on-demand quota is 0 by default.
- [ ] ≥3 MLflow runs with real varied hyperparams + metrics logged.
- [ ] Register final model in Model Registry as `PendingManualApproval` — never auto-approve.
- [ ] Justify `scale_pos_weight` (reference derives 3.545 from the split, don't hardcode).
- [ ] Bootstrap CI (~2000 resamples) on AUC lift vs. recency-only baseline; CI must exclude zero.
- [ ] Slice evaluation per loyalty tier with `n` reported, flag undersized tiers.
- [ ] One chain of numbers: report ⇄ `evaluation_metrics.json` ⇄ an MLflow run ⇄ the registry version's metadata, all matching.

## 5. Task 2 — pick a track

- **Track B (RAG / offer generation):** no starter code, build your own `rag/`. Grading targets were loosened 2026-10-12 — the official thresholds (faithfulness ≥0.80 etc.) are **not** gradable with the provided harness; what's graded now is clean harness execution + honest reporting + one measured improvement. Known install gotcha: `pip install ragas datasets "langchain-community<0.4" langchain-aws` (unpinned installs a broken import). Don't set both `temperature` and `top_p` on Claude 4+ models.
- **Track C (Agent / AgentCore):** separate Terraform root under `infrastructure/environments/agent/` — do not touch the Lab 1-2 root. Three `TODO (student)` items in its `main.tf`. Use the `us.` cross-region inference profile model ID, not the bare ID or Claude 3 Haiku.

## 6. Before submitting

1. Final training run + evaluation, outputs under `docs/lab3-evidence/`.
2. `bash scripts/collect-lab3-evidence.sh --track B` (or `C`) — fix every `FAIL`, rerun.
3. `bash scripts/teardown-lab3.sh` (Track C: run evidence collection *before* this — it deletes the agent stack and its Cedar policies).
4. Commit `docs/` and `notebooks/`, then:
   ```bash
   git tag lab3-submit
   git push origin lab3-submit
   ```
5. Only after fully done with Lab 3 (and evidence is collected): `scripts/teardown-lab2.sh`, accepting that this wipes the Feature Group/bucket for good (fine, since the lab is over) — remember `terraform destroy` alone doesn't fully clean up per Lab 2's own teardown notes.

Never commit `.env`, `terraform.tfvars`, or AWS keys — committed secrets are an automatic zero.
