#!/usr/bin/env bash
# Canary rollback for northstar-churn-prod.
#
# Trigger: alarm northstar-churn-rollback-canary-latency (rollback-alarm.json),
# canary p95 ModelLatency > 200000 microseconds (200 ms) for 3 x 1-minute periods.
#
# Routes 100% of traffic to the champion variant. Takes ~90 s; the endpoint
# reports Updating throughout but keeps serving with no dropped requests.
# This does NOT stop the canary instance billing. Only deleting the endpoint
# (scripts/teardown-lab5.sh) stops the charge.
set -euo pipefail

EP=northstar-churn-prod

aws sagemaker update-endpoint-weights-and-capacities \
  --endpoint-name "$EP" \
  --desired-weights-and-capacities \
    VariantName=champion,DesiredWeight=1 \
    VariantName=canary,DesiredWeight=0

echo "Waiting for $EP to return to InService..."
aws sagemaker wait endpoint-in-service --endpoint-name "$EP"

aws sagemaker describe-endpoint --endpoint-name "$EP" \
  --query 'ProductionVariants[].[VariantName,CurrentWeight]' --output text
