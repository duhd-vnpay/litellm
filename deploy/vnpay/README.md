# VNPay LiteLLM Ops

VNPay-specific deployment, routing hook, và operational config cho LiteLLM Proxy. Folder này nằm trong fork [duhd-vnpay/litellm](https://github.com/duhd-vnpay/litellm) của upstream BerriAI/litellm.

## Stack

- **LiteLLM Proxy** `v1.83.3-stable` — multi-provider LLM gateway
- **Infrastructure**: PostgreSQL (StatefulSet), Redis (Deployment), Nginx Ingress
- **Providers**: VNPAY GenAI on-premise (GLM-4/AIR-4.5), Kimi K2.5 (Anthropic-compat), Claude Sonnet/Opus/Haiku 4.x, MiniMax-M2.7 (Anthropic-compat)
- **Access path**: Client → VNPayCloud WAF → Nginx Ingress (`api-llm.x.vnshop.cloud`) → LiteLLM proxy → Redis cache + PostgreSQL
- **Cluster**: K8s on VNPayCloud (`sdlc-go-k8s-v2`)

## Structure

```
deploy/vnpay/
├── helm/
│   ├── litellm-infra/                  # Postgres + Redis + public Ingress chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   ├── litellm-routing-hook/           # Pre-call intelligent router (Python hook chart)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   ├── hook/
│   │   │   └── vnpay_routing_hook.py   # ← source code, edit here
│   │   └── templates/
│   │       └── configmap.yaml          # Helm render via .Files.Get
│   ├── values-litellm-vnpay.yaml       # Override values cho upstream LiteLLM helm chart
│   ├── litellm-post-upgrade-job.yaml   # Job: patch num_retries cho DB-stored models
│   ├── rbac-litellm-readonly.yaml      # RBAC: read-only access cho ops team
│   └── scripts/
│       ├── litellm-deploy-routing.sh
│       └── litellm-post-upgrade.sh
└── docs/
    ├── litellm-gateway-vnpay-proposal.{md,pdf,docx,jpeg}
    └── superpowers/
        ├── plans/2026-04-01-litellm-enterprise-rollout.md
        └── specs/2026-03-30-litellm-k8s-deployment-design.md
```

## Deploy

```bash
cd deploy/vnpay

# 1. Infrastructure (Postgres + Redis + public ingress)
helm upgrade --install litellm-infra ./helm/litellm-infra -n litellm --create-namespace

# 2. Routing hook chart (render ConfigMap từ hook/vnpay_routing_hook.py)
helm upgrade --install litellm-routing-hook ./helm/litellm-routing-hook -n litellm

# 3. LiteLLM upstream chart với override values
helm upgrade --install litellm oci://ghcr.io/berriai/litellm-helm:1.82.3 \
  -f helm/values-litellm-vnpay.yaml -n litellm --wait --timeout=300s

# 4. Post-upgrade job (apply num_retries cho DB models)
bash helm/scripts/litellm-post-upgrade.sh
```

Hoặc dùng wrapper script:

```bash
bash deploy/vnpay/helm/scripts/litellm-deploy-routing.sh
```

## Routing hook

Pre-call hook tự động phân loại request và route tới provider tối ưu:

| Tier | Trigger | Model | Cost |
|---|---|---|---|
| **0 — Sensitive** | PII keywords (CMND, OTP, card number, PII patterns) | `vnpay-sensitive` (GLM-4 on-premise) | Free, zero egress |
| **1 — Simple** | translate, summarize, format, grammar | `vnpay-simple` (Kimi K2.5) | $0.60/$2.50 per MTok |
| **2 — Medium** | debug, code review, refactor, SQL, analysis | `vnpay-medium` (Kimi K2.5) | $0.60/$2.50 per MTok |
| **3 — Complex** | (default — không match keyword nào) | client choice | varies |

**Override logic**: Hook **chỉ** override khi client gửi model thuộc Claude default (`claude-(sonnet|opus|haiku)-(4|3|3-5|3-7)-*`). Mọi model khác (`MiniMax-M2.7`, `vnpay-*`, `kimi/*`, `v_glm46`, …) được giữ nguyên — tôn trọng client chọn tường minh.

**Edit hook**:
1. Sửa `helm/litellm-routing-hook/hook/vnpay_routing_hook.py`
2. `helm upgrade --install litellm-routing-hook ./helm/litellm-routing-hook -n litellm`
3. `kubectl rollout restart deployment/litellm -n litellm` (nếu hook đã được mount)

## Networking & IP logging

Traffic flow: `Client (public IP) → VNPayCloud WAF → LB (SNAT) → K8s Node → Nginx Ingress → LiteLLM pod`

Để LiteLLM ghi đúng client IP vào spend log:

1. **WAF VNPayCloud** phải forward `X-Forwarded-For` + `X-Real-IP` header
2. **Nginx Ingress**:
   - `nginx.ingress.kubernetes.io/use-forwarded-headers: "true"`
   - `nginx.ingress.kubernetes.io/compute-full-forwarded-for: "true"`
3. **LiteLLM** `general_settings.use_x_forwarded_for: true` (đã set trong `values-litellm-vnpay.yaml`)

Whitelist `nginx.ingress.kubernetes.io/whitelist-source-range` đã **disable** mặc định trong `litellm-infra/values.yaml` (`enforceAllowlist: false`) — vì WAF đã filter tầng trước, và bật allowlist sau khi WAF forward XFF sẽ block public IP của client (false positive). Bật lại nếu cần defense-in-depth.

## Operations

- **Master key**: `kubectl get secret litellm-master-key -n litellm -o jsonpath='{.data.PROXY_MASTER_KEY}' | base64 -d`
- **Provider keys**: stored trong secret `litellm-provider-keys` (Anthropic, Kimi, MiniMax, VNPAY GenAI)
- **Spend log query** (qua DB):
  ```bash
  kubectl exec -n litellm litellm-postgresql-0 -- psql -U litellm -d litellm -c '
    SELECT request_id, model_group, metadata->>'"'"'requester_ip_address'"'"' as ip
    FROM "LiteLLM_SpendLogs" ORDER BY "startTime" DESC LIMIT 10
  '
  ```
- **Tail routing decisions**: `kubectl logs -n litellm -l app=litellm -f | grep '\[routing\]'`

## Known incidents & mitigations

- **2026-04-14 — initdb data loss**: Mount ConfigMap vào `/docker-entrypoint-initdb.d/` + restart pod sẽ trigger initdb và xóa toàn bộ PostgreSQL data. **Không bao giờ** mount script vào path đó. Dùng `ALTER SYSTEM SET ... ; SELECT pg_reload_conf();` để tune Postgres mà không cần restart.
- **MiniMax `output_config` reject**: MiniMax Anthropic endpoint không support `output_config` (structured output). Fix: upstream patch `litellm/llms/minimax/messages/transformation.py` strip param trước khi forward.

## History

- **2026-04-15**: Tách từ repo `git.vnpay.vn/duhd/agentic-coding` qua `git filter-repo` → push lên `github.com/duhd-vnpay/litellm-vnpay` (private)
- **2026-04-15**: Gộp `litellm-vnpay` vào fork `github.com/duhd-vnpay/litellm` qua `git subtree add --prefix=deploy/vnpay`. Repo standalone đã archive read-only.
