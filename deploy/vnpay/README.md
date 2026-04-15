# litellm-vnpay

LiteLLM Gateway deployment cho VNPay — Helm charts, routing hooks, specs, và ops scripts.

## Stack

- **LiteLLM Proxy** `v1.83.3-stable` — multi-provider LLM gateway
- **Infrastructure**: PostgreSQL (statefulset), Redis (deployment), Nginx Ingress
- **Providers**: VNPAY GenAI (on-premise GLM-4/AIR-4.5), Kimi K2.5, Claude Sonnet/Opus/Haiku, MiniMax-M2.7
- **Access**: VNPayCloud WAF → Nginx Ingress → LiteLLM → Redis cache + PostgreSQL
- **Deployment**: Kubernetes on VNPayCloud (`sdlc-go-k8s-v2`)

## Structure

```
helm/
├── litellm-infra/              # Helm chart: PostgreSQL + Redis + public Ingress
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
├── litellm-routing-hook/       # Helm chart: Python pre-call routing hook
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── hook/
│   │   └── vnpay_routing_hook.py   # ← source code (edit here)
│   └── templates/
│       └── configmap.yaml
├── values-litellm-vnpay.yaml   # Override values cho upstream LiteLLM chart
├── litellm-post-upgrade-job.yaml  # Job: patch num_retries cho DB-stored models
├── rbac-litellm-readonly.yaml  # RBAC: read-only access cho ops team
└── scripts/
    ├── litellm-deploy-routing.sh
    └── litellm-post-upgrade.sh

docs/
├── litellm-gateway-vnpay-proposal.md       # Proposal triển khai
├── superpowers/plans/2026-04-01-litellm-enterprise-rollout.md
└── superpowers/specs/2026-03-30-litellm-k8s-deployment-design.md
```

## Deploy

```bash
# 1. Infrastructure (PostgreSQL + Redis + public ingress)
helm upgrade --install litellm-infra ./helm/litellm-infra -n litellm --create-namespace

# 2. Routing hook chart (render ConfigMap từ hook/vnpay_routing_hook.py)
helm upgrade --install litellm-routing-hook ./helm/litellm-routing-hook -n litellm

# 3. LiteLLM upstream chart với override values
helm upgrade --install litellm oci://ghcr.io/berriai/litellm-helm:1.82.3 \
  -f helm/values-litellm-vnpay.yaml -n litellm

# 4. Post-upgrade job (patch num_retries cho DB models)
bash helm/scripts/litellm-post-upgrade.sh
```

## Notes

- Repo tách từ [agentic-coding](https://git.vnpay.vn/duhd/agentic-coding) (2026-04-15) để quản lý LiteLLM ops độc lập
- Lịch sử commit liên quan LiteLLM được giữ nguyên qua `git filter-repo`
