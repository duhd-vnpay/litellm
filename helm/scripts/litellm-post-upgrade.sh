#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# litellm-post-upgrade.sh
# Run after every: helm upgrade litellm ...
#
# Usage:
#   bash helm/scripts/litellm-post-upgrade.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

NAMESPACE="litellm"
JOB_NAME="litellm-post-upgrade"
JOB_FILE="$(dirname "$0")/../litellm-post-upgrade-job.yaml"

echo "==> Deleting stale job (if any)..."
kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --ignore-not-found

echo "==> Applying post-upgrade job..."
kubectl apply -f "$JOB_FILE" -n "$NAMESPACE"

echo "==> Waiting for job to complete (60s timeout)..."
kubectl wait --for=condition=complete job/"$JOB_NAME" \
  -n "$NAMESPACE" --timeout=60s

echo "==> Job output:"
kubectl logs -n "$NAMESPACE" \
  "$(kubectl get pods -n "$NAMESPACE" -l component=post-upgrade -o jsonpath='{.items[-1].metadata.name}')"

echo ""
echo "post-upgrade complete."
