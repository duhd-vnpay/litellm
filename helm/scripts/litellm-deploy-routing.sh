#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# litellm-deploy-routing.sh
# Deploy LiteLLM với Intelligent Routing Hook
#
# Usage:
#   bash helm/scripts/litellm-deploy-routing.sh [helm-chart-path]
#
# Default chart path: oci://ghcr.io/berriai/litellm-helm
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

NAMESPACE="litellm"
RELEASE="litellm"
CHART="${1:-oci://ghcr.io/berriai/litellm-helm}"
VALUES_FILE="$(dirname "$0")/../values-litellm-vnpay.yaml"
HOOK_FILE="$(dirname "$0")/../litellm-routing-hook.yaml"

echo "==> [1/4] Applying routing hook ConfigMap..."
kubectl apply -f "$HOOK_FILE" -n "$NAMESPACE"

echo "==> [2/4] Verifying hook ConfigMap..."
kubectl get configmap litellm-routing-hook -n "$NAMESPACE" \
  -o jsonpath='{.data.vnpay_routing_hook\.py}' | head -5
echo "... (ok)"

echo "==> [3/4] Helm upgrade..."
helm upgrade "$RELEASE" "$CHART" \
  -f "$VALUES_FILE" \
  -n "$NAMESPACE" \
  --wait \
  --timeout=120s

echo "==> [4/4] Verifying hook is mounted in pods..."
POD=$(kubectl get pods -n "$NAMESPACE" -l app=litellm \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n "$NAMESPACE" "$POD" -- ls /etc/litellm/hooks/

echo ""
echo "==> Running post-upgrade job..."
bash "$(dirname "$0")/litellm-post-upgrade.sh"

echo ""
echo "Deploy complete. Tail logs để verify routing:"
echo "  kubectl logs -n $NAMESPACE -l app=litellm -f | grep '\\[routing\\]'"
