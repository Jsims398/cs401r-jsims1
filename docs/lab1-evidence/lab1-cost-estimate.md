# Lab 1 — Monthly Cost Estimate


| Component | Monthly Estimate | Key Assumptions | One Optimization |
|---|---|---|---|
| SageMaker Studio | $2.00 | `ml.t3.medium` JupyterLab app at $0.05/hr, 2 hrs/day, 20 workdays/month = 40 hrs | Enable Studio's idle-shutdown lifecycle config. Could shorten active hours from ~40 to ~10/month, saving ~$1.50/month (75% of this line) |
| S3 storage | $0.12 | 5 GB in `northstar-dev-data-*` (raw/processed/features/artifacts, early-semester volume) at $0.023/GB | — |
| Internet Gateway | $0.02 | 2 GB/month egress (container image pulls, Studio UI) at $0.01/GB | — |
| DynamoDB (state lock) | $0.01 | On-demand capacity, single `LockID` item, near-zero read/write requests per `terraform plan`/`apply` | — |
| S3 state bucket | $0.01 | `northstar-tfstate-*`, versioned `terraform.tfstate` well under 1 MB | — |
| **Total** | **$2.16** | | |

## Assumptions in detail

- **SageMaker Studio** 2 hrs/day at 20 workdays/month reflects one ML engineer doing lab work, not a production training schedule.
- **S3 storage** 5 GB is a starting estimate, not measured usage.
- **Internet Gateway** $0.01/GB is used here per the lab's specified rate. I was unsure what to put for usage here so I said 2GB. 
- **DynamoDB** Near zero but unsure what to price at as it is on-demand. 
- **S3 state bucket** holds a single Terraform state file, versioned. State file size for this module count (17-ish resources) is a few KB; the $0.01 floor reflects billing rounding, not real usage.

## Optimization

**Enable Studio's idle-shutdown lifecycle configuration**, which auto-terminates the KernelGateway/JupyterServer app after a configurable idle period. Manually shutting down Studio only happens if the staff remember. Automating it converts ~40 hrs/month of potential Studio runtime into ~10 hrs of actual working time, cutting the Studio line from $2.00 to about $0.50/month (a 75% reduction on that line, ~70% of the platform's total steady-state cost) while also removing the graded failure mode of a forgotten running instance.
