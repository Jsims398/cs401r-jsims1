#!/bin/bash
# Lab 4 evidence helpers (snap, save_log) from lab4-instructions.md.
# Source from the repo root:  source scripts/lab4-evidence.sh
#
# Adapted for Git Bash on Windows: MSYS_NO_PATHCONV stops "/aws/codebuild/..."
# being rewritten into a Windows path, PYTHONUTF8 lets the AWS CLI print the
# build log's non-ASCII characters, and python3 falls back to the py launcher.

export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
PY=$(command -v python3 >/dev/null 2>&1 && python3 -c '' 2>/dev/null && echo python3 || echo "py -3")

TOPIC=$(aws cloudformation describe-stacks --stack-name northstar-cicd \
  --query "Stacks[0].Outputs[?OutputKey=='ModelApprovalTopicArn'].OutputValue" --output text)

snap () {   # usage: snap "LABEL"  -> appends a labelled snapshot to docs/lab4-failure-demo.txt
  {
    echo; echo "===== $1  ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ====="
    echo "--- newest CodeBuild build: id, commit, status, then phases"
    B=$(aws codebuild list-builds-for-project --project-name northstar-ci --query 'ids[0]' --output text)
    aws codebuild batch-get-builds --ids "$B" --query 'builds[0].[id,resolvedSourceVersion,buildStatus]' --output text
    aws codebuild batch-get-builds --ids "$B" --query 'builds[0].phases[].[phaseType,phaseStatus]' --output text
    echo "--- newest 3 model packages"
    aws sagemaker list-model-packages --model-package-group-name northstar-churn-models \
      --sort-by CreationTime --sort-order Descending --max-results 3 \
      --query 'ModelPackageSummaryList[].[ModelPackageVersion,ModelApprovalStatus,CreationTime]' --output text
    echo "--- alarm state"
    aws cloudwatch describe-alarms --alarm-names northstar-ci-build-failure \
      --query 'MetricAlarms[0].[StateValue,StateUpdatedTimestamp]' --output text
    echo "--- alarm action history"
    aws cloudwatch describe-alarm-history --alarm-name northstar-ci-build-failure \
      --history-item-type Action --max-records 5 --query 'AlarmHistoryItems[].[Timestamp,HistorySummary]' --output text
    echo "--- SNS subscriptions (an ARN, not PendingConfirmation)"
    aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" --query 'Subscriptions[].[Protocol,SubscriptionArn]' --output text
  } 2>&1 | tee -a docs/lab4-failure-demo.txt
}

save_log () {   # usage: save_log <codebuild-build-id> <output-file>
  read -r G S <<< "$(aws codebuild batch-get-builds --ids "$1" \
      --query 'builds[0].logs.[groupName,streamName]' --output text)"
  aws logs filter-log-events --log-group-name "$G" --log-stream-names "$S" --output json \
    | $PY -c 'import json,sys; sys.stdout.reconfigure(encoding="utf-8"); sys.stdout.write("".join(e["message"] if e["message"].endswith("\n") else e["message"]+"\n" for e in json.load(sys.stdin)["events"]))' \
    > "$2"
}
