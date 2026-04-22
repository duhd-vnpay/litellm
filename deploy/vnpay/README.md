# VNPay LiteLLM Ops

VNPay-specific deployment, routing hook, và operational config cho LiteLLM Proxy. Folder này nằm trong fork [duhd-vnpay/litellm](https://github.com/duhd-vnpay/litellm) của upstream BerriAI/litellm.

> **End-user guide** (đăng nhập, tạo virtual key, cấu hình Claude Code / Cline / Xcode / Qwen Code / Aider / ...) — xem [USER_GUIDE.md](./USER_GUIDE.md).

## Architecture

```
                                        ┌─────────────────────────────────────────────┐
                                        │              LiteLLM Namespace              │
                                        │                                             │
Client (claude-cli, Copilot, etc.)      │  ┌─────────┐    ┌──────────┐                │
  │                                     │  │ LiteLLM │───▶│ PgBouncer│──▶ PostgreSQL  │
  ▼                                     │  │ Pod ×2  │    │(session) │   (StatefulSet)│
VNPayCloud WAF/CDN (600s)               │  │         │    └──────────┘    15Gi PVC    │
  │                                     │  │ Routing  │                                │
  ▼                                     │  │  Hook   │───▶ Redis (cache)              │
CDN Edge sunny.edgevnpay.vn (600s)      │  └────┬────┘                                │
  │                                     │       │ OTLP gRPC                            │
  ▼                                     └───────┼──────────────────────────────────────┘
VNPayCloud LB (TCP passthrough)                 │                    │
  │                                             ▼                    ▼
  ▼                                     ┌───────────────┐   ┌───────────────────┐
K8s NodePort 30443                      │ LLM Providers │   │ Jaeger (sdlc-go-  │
  │                                     │               │   │ prod:4317) Tracing│
  ▼                                     │  Tier 0: VNPAY GenAI (on-prem, $0)   │
Nginx Ingress (600s)                    │    └─ MiniMax M2.7 (vnpay-sensitive)  │
  │                                     │    └─ MiniMax M2.7 (vnpay/minimax)   │
  ▼                                     │  Tier 1: MiniMax (vnpay-simple, $0)  │
LiteLLM Proxy (600s)                    │  Tier 2: Kimi K2.5 ($0.60/$3 MTok)  │
                                        │    └─ 3 API keys, load balanced      │
                                        │  Tier 3: Claude Sonnet/Opus 4.x      │
                                        │  Embedding: BGE-M3 (on-prem, $0)    │
                                        └───────────────────────────────────────┘
```

### Timeout Chain (đồng bộ 600s)

| Layer | Timeout | Config |
|---|---|---|
| WAF/CDN Origin | 600s | WAF portal |
| CDN Edge Dynamic Proxy | 600s | WAF portal |
| VNPayCloud LB | N/A (TCP passthrough) | `loadbalancer.tf` |
| Nginx Ingress | 600s | Ingress annotations `proxy-read-timeout` |
| LiteLLM `request_timeout` | 600s | `proxy_server_config.yaml` → `litellm_settings` |

### Database Connection Chain

```
LiteLLM Pod (Prisma, connection_limit=10, pool_timeout=30s)
  → PgBouncer (session pooling, max_client=200, pool_size=20, idle_timeout=600s)
    → PostgreSQL 16 (max_connections=100, idle_in_tx_timeout=5min, statement_timeout=5min)
```

## Stack

- **LiteLLM Proxy** `v1.83.3-stable` (digest pinned) — multi-provider LLM gateway (HPA 2-6 replicas @ 70% CPU)
- **Infrastructure**: PostgreSQL 16 (StatefulSet, 15Gi PVC), Redis 7 (Deployment), PgBouncer session pooling (Deployment), Nginx Ingress
- **Auth (UI)**: Google SSO via oauth2-proxy v7.7.1 — domain `@vnpay.vn`, nginx `auth_request`, `/vnpay-sso` auto-login endpoint
- **Providers**: VNPAY GenAI on-premise (GLM-4, MiniMax M2.7), Kimi K2.5 (3 keys load-balanced), Claude Sonnet/Opus/Haiku 4.x, BGE-M3 embedding
- **Access path**: Client → VNPayCloud WAF/CDN → CDN Edge → LB → Nginx Ingress → LiteLLM → Provider
- **Cluster**: K8s on VNPayCloud (`sdlc-go-k8s-v2`)

## Structure

```
deploy/vnpay/
├── helm/
│   ├── litellm-infra/                  # Postgres + Redis + PgBouncer + public Ingress chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   │       ├── deployments/
│   │       │   ├── redis.yaml
│   │       │   └── pgbouncer.yaml      # PgBouncer connection pooler
│   │       ├── stateful/
│   │       │   └── postgresql.yaml
│   │       └── ingress-public.yaml
│   ├── litellm-routing-hook/           # Pre-call intelligent router + SSO handler (Python hook chart)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   ├── hook/
│   │   │   ├── vnpay_routing_hook.py   # ← routing hook source, edit here
│   │   │   ├── vnpay_sso_handler.py    # ← Google SSO /vnpay-sso + Teleport /teleport-sso
│   │   │   ├── vnpay_premium_unlock.py # ← set proxy_server.premium_user=True (unlock audit log, enterprise UI)
│   │   │   └── vnpay_splunk_audit.py   # ← CustomLogger đẩy audit log → Splunk HEC
│   │   └── templates/
│   │       └── configmap.yaml          # Helm render via .Files.Get
│   ├── values-litellm-vnpay.yaml       # Override values cho upstream LiteLLM helm chart
│   ├── oauth2-proxy.yaml               # oauth2-proxy Deployment + Service (Google SSO)
│   ├── ingress-oauth2-proxy.yaml       # Ingress cho /oauth2/* (không có auth-url)
│   ├── litellm-health-cronjob.yaml     # CronJob: health check + 24h usage stats (*/5min)
│   ├── litellm-post-upgrade-job.yaml   # Job: patch num_retries cho DB-stored models
│   ├── rbac-litellm-readonly.yaml      # RBAC: read-only access cho ops team
│   ├── networkpolicy-litellm-jaeger-egress.yaml  # NetworkPolicy: allow OTLP → Jaeger sdlc-go-prod
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

# 1. Infrastructure (Postgres + Redis + PgBouncer + public ingress)
helm upgrade --install litellm-infra ./helm/litellm-infra -n litellm --create-namespace

# 2. Routing hook chart (render ConfigMap từ hook/vnpay_routing_hook.py)
helm upgrade --install litellm-routing-hook ./helm/litellm-routing-hook -n litellm

# 3. LiteLLM upstream chart với override values
# --take-ownership --force-conflicts: cần khi có drift với kubectl-set/annotate
# hoặc kubectl-client-side-apply (xem incident 2026-04-20)
helm upgrade --install litellm oci://ghcr.io/berriai/litellm-helm --version 1.82.3 \
  -f helm/values-litellm-vnpay.yaml -n litellm \
  --take-ownership --force-conflicts --wait --timeout=5m

# 4. Post-upgrade job (apply num_retries cho DB models)
bash helm/scripts/litellm-post-upgrade.sh
```

### Quick deploy routing hook only (no helm)

```bash
kubectl create configmap litellm-routing-hook \
  --from-file=vnpay_routing_hook.py=helm/litellm-routing-hook/hook/vnpay_routing_hook.py \
  --from-file=vnpay_sso_handler.py=helm/litellm-routing-hook/hook/vnpay_sso_handler.py \
  -n litellm --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment litellm -n litellm
```

## Google SSO (UI Only)

UI tại `litellm.x.vnshop.cloud` yêu cầu đăng nhập Google `@vnpay.vn`. API tại `api-llm.x.vnshop.cloud` không bị ảnh hưởng.

### Two supported flows

**Flow 1 — Teleport App Access** (khi truy cập qua Teleport, production):

```
Browser → litellm.x.vnshop.cloud (Teleport)
  → Teleport Google SSO
  → Teleport inject `Teleport-Jwt-Assertion` header, forward → /teleport-sso
  → LiteLLM decode JWT → extract email → lookup user_role từ DB
  → set `token` cookie (JWT) → redirect /ui/?login=success
  → UI đọc cookie → accessToken context → API calls thành công
```

**Flow 2 — oauth2-proxy** (fallback, không qua Teleport):

```
Browser → nginx auth_request → oauth2-proxy /oauth2/auth
  → Google OAuth (vnpay.vn domain only)
  → oauth2-proxy set cookie → forward `X-Auth-Request-Email` → /vnpay-sso
  → LiteLLM tạo session → set cookie → redirect /ui/?login=success
```

### Handoff pattern (quan trọng)

Phải **match chính xác** LiteLLM native SSO:
- Cookie-only (không truyền token trong URL) — tránh race condition UI fire `/models` trước khi useEffect đọc URL
- Redirect `/ui/?login=success` với **trailing slash** — không có slash sẽ bị LiteLLM StaticFiles auto-redirect 307 dùng `request.base_url` = HTTP nội bộ → mixed content warning khi page đang HTTPS
- JWT payload field name `key` (không phải `id`) — match `ReturnedUITokenObject` schema, backend auth dùng `jwt["key"]` để lookup API token
- JWT `user_role` đọc từ DB qua `_lookup_user_role()` — preserve `proxy_admin` qua các lần login, không hardcode `app_user`
- SSO endpoint accept GET + POST + HEAD — Teleport có thể probe bằng HEAD, proxy-initiated POST

### Components

| Component | File | Notes |
|---|---|---|
| `oauth2-proxy` | `oauth2-proxy.yaml` | Google provider, `--email-domain=vnpay.vn`, `--set-xauthrequest=true` |
| `/oauth2/*` ingress | `ingress-oauth2-proxy.yaml` | Không có auth-url annotation — oauth2-proxy tự handle |
| LiteLLM ingress | `values-litellm-vnpay.yaml` → `ingress.annotations` | `auth-url`, `auth-signin`, `auth-snippet` (Bearer bypass) |
| SSO handler | `hook/vnpay_sso_handler.py` | Đăng ký `/teleport-sso` + `/vnpay-sso` routes lên FastAPI |

### User identity convention

Tất cả user (cả invited UI lẫn SSO-created) phải có `user_id = email`. Users cũ tạo qua UI invite có `user_id = UUID` — đã migrate sang email (xem incident 2026-04-18 migration) và cascade update các FK:
- `LiteLLM_VerificationToken.user_id/created_by/updated_by`
- `LiteLLM_SpendLogs."user"`, `LiteLLM_DailyUserSpend.user_id`
- `LiteLLM_TeamTable.members_with_roles` (JSON array)
- `LiteLLM_InvitationLink`, `LiteLLM_OrganizationMembership` (auto qua FK `ON UPDATE CASCADE`)

### Bearer token bypass

API calls với `Authorization: Bearer sk-xxx` bỏ qua OAuth hoàn toàn (nginx `auth-snippet`). Programmatic access từ `litellm.x.vnshop.cloud` vẫn hoạt động.

### Secrets

```bash
# Tạo secret oauth2-proxy (Google Client ID/Secret + cookie secret)
kubectl create secret generic litellm-oauth2-proxy-secret -n litellm \
  --from-literal=OAUTH2_PROXY_CLIENT_ID="<google-client-id>" \
  --from-literal=OAUTH2_PROXY_CLIENT_SECRET="<google-client-secret>" \
  --from-literal=OAUTH2_PROXY_COOKIE_SECRET="<32-char-random-string>"
```

Cookie secret phải là chuỗi 16/24/32 ký tự (raw bytes, KHÔNG phải base64).

## Routing Hook

Pre-call hook tự động phân loại request và route tới provider tối ưu:

| Tier | Trigger | Model | Cost |
|---|---|---|---|
| **0 — Sensitive** | PII keywords (CMND, OTP, card number, PII patterns) | `vnpay-sensitive` (GLM-4 on-premise) | Free, zero egress |
| **1 — Simple** | translate, summarize, format, grammar | `vnpay-simple` (Kimi K2.5) | $0.60/$3.00 per MTok |
| **2 — Medium** | debug, code review, refactor, SQL, analysis | `vnpay-medium` (Kimi K2.5) | $0.60/$3.00 per MTok |
| **3 — Complex** | (default — không match keyword nào) | client choice | varies |

**Override logic**: Hook **chỉ** override khi client gửi model thuộc Claude default (`claude-(sonnet|opus|haiku)-(4|3|3-5|3-7)-*`). Mọi model khác (`MiniMax-M2.7`, `vnpay-*`, `kimi/*`, `v_glm46`, …) được giữ nguyên — tôn trọng client chọn tường minh.

### Hook features

| Feature | Description |
|---|---|
| **Team alias redirect** | Teams trong `TEAM_CLAUDE_TO_KIMI_ALIASES` (DVNH, DVTT, GSVH, THHT, TTKHDL, UDDD, eFIN) → redirect Claude → Kimi K2.5 |
| **Custom pricing injection** | Force-set `litellm.model_cost` mỗi pre_call cho MiniMax-M2/M2.7, openai/minimax, openai/v_glm46, openai/v_search, moonshot/kimi-k2.6 (~nanoseconds, idempotent). Chống 2 nguồn wipe/đè: periodic `_check_and_reload_model_cost_map` + DB ProxyModelTable sync (encrypted `litellm_params.input_cost_per_token=0.0` khi thêm model qua UI thiếu cost) |
| **Reasoning model flag** | `supports_reasoning: True` cho `moonshot/kimi-k2.6` (+ `kimi-k2.5` đã có upstream) — trigger `fill_reasoning_content()` inject `reasoning_content: " "` placeholder vào assistant tool_call messages. Cần thiết vì Claude Code / Anthropic SDK không round-trip `thinking` blocks sang OpenAI `reasoning_content` format → Moonshot reject 400 "thinking is enabled but reasoning_content is missing" |
| **Kimi temperature fix** | Force `temperature=1` cho reasoning models (Kimi K2.5) |
| **Kimi max_tokens** | Default `max_tokens=16384` nếu client không set hoặc set thấp hơn |
| **MiniMax max_tokens** | Default `max_tokens=16384`, strip `output_config` (unsupported) |
| **Orphan tool_call sanitize** | Strip orphan `tool_calls` và tool responses từ conversation history — tránh Kimi 400 error khi client truncate history |

## Models

### Config-based (values-litellm-vnpay.yaml)

| Model Name | Provider | Cost | Notes |
|---|---|---|---|
| `vnpay-sensitive` | VNPAY GenAI MiniMax M2.7 | $0 | On-premise, zero egress |
| `v_glm46` | VNPAY GenAI GLM-4 | $0 | Legacy alias (backward compat) |
| `vnpay/minimax` | VNPAY GenAI MiniMax M2.7 | $0 | On-premise, 131K ctx, thinking support |
| `vnpay-simple` | VNPAY GenAI MiniMax M2.7 | $0 | On-premise, simple tasks |
| `vnpay-medium` | Kimi K2.5 | $0.60/$3.00 MTok | Coding/analysis, 262K ctx |
| `claude-sonnet` | Anthropic Claude Sonnet 4.6 | $3/$15 MTok | Complex reasoning |
| `claude-opus` | Anthropic Claude Opus 4.6 | $15/$75 MTok | Deep reasoning |
| `text-embedding-3-small` | VNPAY GenAI BGE-M3 | $0 | 1024 dims, on-premise |

### DB-stored models (added via UI/API)

Kimi K2.5 (3 keys load-balanced), Claude Haiku/Sonnet/Opus variants, MiniMax-M2.7 (cloud). Managed via `store_model_in_db: true`.

## Fallback Chain

```
claude-opus → claude-sonnet → vnpay-medium → vnpay-simple
moonshot/kimi-k2.5 → vnpay/minimax (on-premise)

Context window overflow:
  vnpay-simple (128K) → claude-sonnet
  vnpay-medium (128K) → claude-sonnet
```

## Networking & IP Logging

Traffic flow: `Client (public IP) → VNPayCloud WAF/CDN → CDN Edge → LB (SNAT) → K8s Node → Nginx Ingress → LiteLLM pod`

Để LiteLLM ghi đúng client IP vào spend log:

1. **WAF VNPayCloud** phải forward `X-Forwarded-For` + `X-Real-IP` header
2. **Nginx Ingress**:
   - `nginx.ingress.kubernetes.io/use-forwarded-headers: "true"`
   - `nginx.ingress.kubernetes.io/compute-full-forwarded-for: "true"`
3. **LiteLLM** `general_settings.use_x_forwarded_for: true`

## Operations

### Secrets

- **Master key**: `kubectl get secret litellm-master-key -n litellm -o jsonpath='{.data.PROXY_MASTER_KEY}' | base64 -d`
- **Provider keys**: stored trong secret `litellm-provider-keys` (Anthropic, Kimi, MiniMax, VNPAY GenAI, Redis)
- **DB credentials**: secret `litellm-postgres-credentials`

### Audit Log

LiteLLM ghi mọi thay đổi entity (team, user, key, model, MCP server, v.v.) vào bảng `LiteLLM_AuditLog`. Tính năng này bị license-gate trên OSS — VNPay bypass qua 2 hook:

| Hook | File | Tác dụng |
|---|---|---|
| `vnpay_premium_unlock` | `hook/vnpay_premium_unlock.py` | (1) Set `proxy_server.premium_user = True` → backend gate ở [audit_logs.py:175](../../litellm/proxy/management_helpers/audit_logs.py#L175) và endpoint `/audit` (package `litellm_enterprise`) pass. (2) Monkey patch `_authorize_and_filter_teams` → proxy_admin với `user_id=self` query (kiểu UI luôn gọi) trả tất cả teams thay vì filter by membership → dropdown Teams trong dialog Policy Attachment hiện đủ |
| `vnpay_sso_handler` | `hook/vnpay_sso_handler.py` | JWT payload `premium_user: true` → UI unlock trang Audit Logs (UI gate client-side decode JWT cookie) |
| `vnpay_splunk_audit` | `hook/vnpay_splunk_audit.py` | `CustomLogger.async_log_audit_log_event` đẩy `StandardAuditLogPayload` → Splunk HEC real-time |

**Config** (xem `values-litellm-vnpay.yaml` → `litellm_settings`):

```yaml
litellm_settings:
  store_audit_logs: true
  audit_log_callbacks:
    - vnpay_splunk_audit.vnpay_splunk_audit   # dotted module name, KHÔNG absolute path
```

Gotcha: handler `audit_log_callbacks` (proxy_server.py:3160) gọi `get_instance_fn` **không** truyền `config_file_path` → phải dùng dotted Python module name (PYTHONPATH=`/etc/litellm/hooks` đã wire sẵn). Dùng absolute path `/etc/litellm/hooks/xxx.xxx` sẽ crash pod với `ImportError`.

**Splunk HEC secret** (tạo khi HEC ready):

```bash
kubectl create secret generic litellm-splunk-hec -n litellm \
  --from-literal=SPLUNK_HEC_URL="https://splunk.vnpay.vn:8088/services/collector" \
  --from-literal=SPLUNK_HEC_TOKEN="<hec-token-uuid>" \
  --from-literal=SPLUNK_HEC_INDEX="litellm_audit" \
  --from-literal=SPLUNK_HEC_VERIFY_TLS="true" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/litellm -n litellm
```

Nếu secret thiếu URL/TOKEN, exporter tự disable (log WARNING, không break proxy).

**Query bằng psql**:

```bash
kubectl exec -n litellm litellm-postgresql-0 -- psql -U litellm -d litellm -c '
  SELECT updated_at, changed_by, action, table_name, object_id
  FROM "LiteLLM_AuditLog"
  ORDER BY updated_at DESC LIMIT 20'
```

`table_name` thường gặp: `LiteLLM_TeamTable`, `LiteLLM_UserTable`, `LiteLLM_VerificationToken`, `LiteLLM_ProxyModelTable`, `LiteLLM_MCPServerTable`. `action`: `created | updated | deleted | rotated | regenerated | blocked | unblocked`.

### Autoscaling

HPA CPU-based (dùng `metrics-server` sẵn có, không cần Prometheus):

```yaml
# values-litellm-vnpay.yaml
autoscaling:
  enabled: true
  minReplicas: 2            # HA floor
  maxReplicas: 6            # 6 × 1 CPU request = 6 CPU cap
  targetCPUUtilizationPercentage: 70
```

Khi bật, chart bỏ qua `.spec.replicas` trong Deployment, HPA manage pod count. Cooldown mặc định 5 phút scale-down (tránh flapping).

**Giới hạn**: LLM proxy I/O-bound (chờ upstream), CPU không luôn phản ánh đúng load. Nếu thấy latency cao mà HPA không scale, upgrade lên KEDA + Prometheus với request-rate trigger (`litellm_request_total`/pod).

```bash
kubectl get hpa -n litellm
kubectl describe hpa litellm -n litellm   # check scale events
```

### Health & Monitoring

- **Health CronJob**: `litellm-health-check` — runs */5min, checks liveliness, readiness, PVC usage, 24h spend stats
- **Backup CronJob**: `litellm-pg-backup` — daily 02:00 UTC, pg_dump to PVC (excluding `LiteLLM_SpendLogs` + `LiteLLM_SpendLogToolIndex` — ~95% DB size, SpendLogs retention 7d tự xóa → không cần re-backup mỗi ngày). Backup size ~600KB thay vì ~1.4GB, chạy <5s thay vì 5min. Retention 7 bản rolling (glob `litellm-backup-[0-9]*.dump`, không đụng milestone dumps `-pre-*` hoặc lightweight `-nospend-*`). Cần full dump với spend history → xem skill `vnpay-litellm-backup-db` hoặc chạy ad-hoc `pg_dump` không kèm `--exclude-table-data` flags
- **SpendLogs cleanup**: Built-in, `maximum_spend_logs_retention_period: 7d`, runs 03:00 UTC daily
- **Nginx log format**: Includes `rt=` (request time), `uct=` (upstream connect time), `urt=` (upstream response time)
- **Distributed tracing**: OpenTelemetry → Jaeger `sdlc-go-prod:4317` (service: `litellm-gateway`, OTLP gRPC)
- **Log aggregation**: Promtail (DaemonSet trong `sdlc-go-prod`) scrape `/var/log/pods/litellm_*/*/*.log` → Loki. Labels: `level`, `log_type` (access/internal), `http_method`, `http_path`, `http_status`, `status_class` (2xx/3xx/4xx/5xx), `endpoint_type` (llm/health/admin/spend). Config managed bởi chart `sdlc-go` (`helm/sdlc-go/templates/deployments/promtail.yaml`) — **không phải bởi repo này**

### Useful commands

```bash
# Spend log query
kubectl exec -n litellm litellm-postgresql-0 -- psql -U litellm -d litellm -c '
  SELECT request_id, model_group, status, spend,
         EXTRACT(EPOCH FROM ("endTime" - "startTime")) as seconds
  FROM "LiteLLM_SpendLogs" ORDER BY "startTime" DESC LIMIT 10'

# Tail routing decisions
kubectl logs -n litellm -l app.kubernetes.io/name=litellm -f | grep '\[routing\]'

# DB connections via PgBouncer
kubectl exec -n litellm litellm-postgresql-0 -- psql -U litellm -d litellm -c \
  "SELECT client_addr, count(*) FROM pg_stat_activity WHERE datname='litellm' GROUP BY 1"

# Manual backup
kubectl create job -n litellm pg-backup-manual --from=cronjob/litellm-pg-backup
```

## Known Incidents & Mitigations

| Date | Incident | Root Cause | Fix |
|---|---|---|---|
| 2026-04-14 | initdb data loss | Mount ConfigMap vào `/docker-entrypoint-initdb.d/` + restart → initdb xóa data | Không mount vào initdb path |
| 2026-04-16 | PostgreSQL data loss on pod reschedule | PVC mount `/var/lib/postgresql` nhưng PGDATA ở `/var/lib/postgresql/data` → data trong overlay | Fix mountPath = PGDATA, explicit PGDATA env |
| 2026-04-17 | Prisma "Client not connected" | Direct DB connection, no keepalive, no pool | Deploy PgBouncer, add Prisma pool params |
| 2026-04-17 | Kimi 400 "tool_call_id not found" | Client truncate history, orphan tool_calls | Sanitize in routing hook |
| 2026-04-17 | Kimi output truncated (8K reasoning, 1 text) | Default max_tokens=8192 too low for reasoning model | Hook force max_tokens=16384 |
| 2026-04-17 | WAF 504 timeout 50s | CDN Edge dynamic proxy hardcoded 50s | Escalated to VNPayCloud infra, increased to 600s |
| 2026-04-18 | NetworkPolicy egress block Redis/DNS | Egress NP trên litellm namespace chặn toàn bộ egress (Redis, DNS, PgBouncer) | Chuyển sang Ingress NP trên sdlc-go-prod thay vì Egress NP trên litellm |
| 2026-04-18 | vnpay_sso_handler ImportError | `get_instance_fn` resolve path relative to config dir (`/etc/litellm/`) nhưng file chỉ mount ở `/etc/litellm/hooks/` | Thêm subPath volumeMount tại `/etc/litellm/vnpay_sso_handler.py` |
| 2026-04-18 | Prisma migrate advisory lock timeout | PgBouncer transaction mode không giữ session → `pg_advisory_lock` timeout mỗi restart | Chuyển PgBouncer sang session pooling mode |
| 2026-04-18 | SSO user luôn hiện non-admin | Handler hardcode `user_role="app_user"` cho generate_key + JWT — override DB role mỗi login | `_lookup_user_role()` query DB trước khi encode JWT |
| 2026-04-18 | UI `Bearer undefined` 401 dù JWT đúng role | JWT dùng field `id` nhưng backend auth đọc `jwt["key"]` (ReturnedUITokenObject schema) → không lookup được API token | Đổi field `id` → `key` trong JWT payload |
| 2026-04-18 | UI race: `/models` 401 trước khi useEffect đọc URL | Token trong URL `?token=...` — UI fire `/models` trước khi xử lý URL param | Cookie-only handoff, redirect `/ui/?login=success` (match native) |
| 2026-04-18 | Mixed content warning khi redirect /ui | Redirect `/ui` (no slash) trigger StaticFiles 307 → `request.base_url` = HTTP internal → Location `http://...` khi page HTTPS | Redirect `/ui/?login=success` với trailing slash, skip auto-redirect |
| 2026-04-18 | UI-invited users có user_id=UUID conflict với SSO user_id=email | Gây duplicate record/cô lập keys+spend khi user login SSO lần đầu | Migration: UPDATE PK + cascade FK cho 13 users (VerificationToken, SpendLogs 11.9K, DailyUserSpend, TeamTable.members_with_roles JSON) |
| 2026-03-24 | Supply chain compromise v1.82.7/v1.82.8 | TeamPCP credential stealer in upstream | Pin image digest, IOC scan trước upgrade |
| 2026-04-20 | Helm release `litellm` FAILED (rev 41) không upgrade được | Drift: `kubectl set env DATABASE_URL` + `kubectl annotate` các snippet Ingress → field manager conflict với helm (Apply) | Sync drift vào values (pgbouncer=true, Teleport JWT bypass), dùng `--take-ownership --force-conflicts` (Helm 3.18+) |
| 2026-04-20 | UI Audit Logs hiện "Enterprise Feature" dù backend đã unlock | UI gate client-side decode JWT cookie → đọc field `premium_user`; SSO handler hardcode `False` | Đổi SSO JWT payload `premium_user: true` + logout/login lại |
| 2026-04-20 | `audit_log_callbacks` pod crash `ImportError` | Handler (proxy_server.py:3160) không truyền `config_file_path` cho `get_instance_fn` → absolute path `/etc/litellm/hooks/...` không import được | Dùng dotted module name (`vnpay_splunk_audit.vnpay_splunk_audit`), PYTHONPATH đã trỏ `/etc/litellm/hooks` |
| 2026-04-21 | UI dialog Policy Attachment dropdown Teams rỗng dù admin có 12 teams | `_authorize_and_filter_teams` (team_endpoints.py:3645) filter by membership bất kể role khi `user_id` được truyền. UI `teamListCall` luôn truyền userId → admin thuộc 0 team thì rỗng | Monkey patch trong `vnpay_premium_unlock`: proxy_admin → trả all teams, bypass user_id filter |
| 2026-04-21 | Kimi K2.6 request fail 400 "thinking is enabled but reasoning_content is missing" | K2.6 bật thinking default + strict validation. LiteLLM có sẵn `fill_reasoning_content()` inject placeholder nhưng chỉ chạy khi `supports_reasoning(model)==True`. K2.6 chưa có trong upstream model_cost | Đăng ký `moonshot/kimi-k2.6` + `kimi-k2.6` vào `_CUSTOM_MODEL_COST` với `supports_reasoning: True` + pricing ($0.95/$4 per MTok, cache hit $0.16/MTok) |
| 2026-04-21 | Cost tracking `moonshot/kimi-k2.6` = 0 dù DB model_info có pricing đúng | (1) Hook re-inject chỉ check `if model not in litellm.model_cost` — DB sync ghi entry zero cost đè hook → key tồn tại → skip. (2) Encrypted `litellm_params.input_cost_per_token=0.0` ưu tiên hơn `model_info` tại cost calc time — default 0 khi model thêm qua UI thiếu cost field | (1) Force-set `_CUSTOM_MODEL_COST` unconditional mỗi pre_call. (2) PATCH `/model/{id}/update` qua API để re-encrypt `litellm_params` với cost đúng. Backfill 88 SpendLogs rows ($2.24) + re-aggregate DailyUserSpend/DailyTeamSpend + UserTable/TeamTable/VerificationToken cumulative |

## History

- **2026-04-15**: Tách từ repo `git.vnpay.vn/duhd/agentic-coding` qua `git filter-repo` → push lên `github.com/duhd-vnpay/litellm-vnpay` (private)
- **2026-04-15**: Gộp `litellm-vnpay` vào fork `github.com/duhd-vnpay/litellm` qua `git subtree add --prefix=deploy/vnpay`. Repo standalone đã archive read-only.
- **2026-04-17**: Deploy PgBouncer, Kimi 3-key load balance, BGE-M3 embedding, SpendLogs retention 7d, timeout chain đồng bộ 600s.
- **2026-04-18**: Pin image digest (IoC verify sau supply chain alert), OpenTelemetry → Jaeger sdlc-go-prod:4317.
- **2026-04-18**: Google SSO cho UI `litellm.x.vnshop.cloud` — oauth2-proxy + `/vnpay-sso` auto-login endpoint, domain `@vnpay.vn`, API endpoint `api-llm.x.vnshop.cloud` không bị ảnh hưởng. Fix PgBouncer session mode (Prisma advisory lock compat).
- **2026-04-18**: Thêm `/teleport-sso` endpoint (Teleport App Access via `Teleport-Jwt-Assertion` header), SSO handler preserve role từ DB thay vì hardcode `app_user`, JWT payload match `ReturnedUITokenObject` schema (`key` field), cookie-only handoff `/ui/?login=success`. Migration `user_id` UUID → email cho 13 UI-invited users (cascade FK + FK auto-update + 11.9K SpendLogs + `members_with_roles` JSON).
- **2026-04-18**: Promtail extract thêm `http_status` + `status_class` cho LiteLLM access logs. Config chuyển về chart `sdlc-go` (owner duy nhất) — không còn duplicate trong repo này.
- **2026-04-20**: Unlock Audit Log trên OSS — `vnpay_premium_unlock` override `proxy_server.premium_user=True` (backend), SSO JWT `premium_user: true` (UI). Thêm `vnpay_splunk_audit` `CustomLogger` push audit log → Splunk HEC real-time (self-disable khi secret `litellm-splunk-hec` chưa cấu hình). Sync 2 drift trong values file: `db.url` thêm `pgbouncer=true` (Prisma simple protocol), `auth-snippet` thêm bypass OAuth cho Teleport JWT. Helm upgrade dùng `--take-ownership --force-conflicts` để dẹp conflict với `kubectl-set`/`kubectl-annotate`/`kubectl-client-side-apply`.
- **2026-04-21**: Mở rộng `vnpay_premium_unlock` thành "landing pad" cho module-level monkey patch OSS gaps. Thêm patch `_authorize_and_filter_teams` → proxy_admin với `user_id=self` (kiểu UI luôn gọi) trả all teams thay vì filter membership → dropdown Teams trong dialog Policy Attachment hiện đủ 12 teams.
- **2026-04-21**: Kimi K2.6 integration — đăng ký pricing ($0.95/$4 per MTok, cache hit $0.16) + `supports_reasoning: True` vào routing hook để trigger `fill_reasoning_content()` placeholder injection (Claude Code / Anthropic SDK không round-trip thinking blocks). Đổi logic re-inject từ "only-if-missing" sang force-override mỗi pre_call — fix case DB ProxyModelTable sync ghi `litellm_params.input_cost_per_token=0.0` đè hook. Update model qua API để re-encrypt `litellm_params`. Backfill 88 SpendLogs rows ($2.24) + daily aggregates + cumulative spend cho users/teams/keys.
- **2026-04-21**: Enable HPA CPU-based autoscaling (minReplicas=2, maxReplicas=6, target 70%) dùng `metrics-server` sẵn có. Traffic hiện tại <2% CPU nên chỉ là preparedness — path nâng cấp sang KEDA + Prometheus request-rate trigger khi cần signal chính xác hơn cho I/O-bound workload.
- **2026-04-22**: Rewrite daily backup CronJob để exclude `LiteLLM_SpendLogs` + `LiteLLM_SpendLogToolIndex` (~95% size DB, 2.67GB → SpendLogs retention 7d built-in tự xóa, không cần re-backup mỗi ngày). Backup size 1.4GB → 623KB (-99.96%), duration 5min → 6s. Retention glob refine thành `litellm-backup-[0-9]*.dump` để không đụng milestone dumps (`-pre-userid-migration-*`) và lightweight ad-hoc (`-nospend-*`). Thêm skill `vnpay-litellm-backup-db` để chạy ad-hoc lightweight dump (~500-700KB, <5s) trước các thao tác migration/cleanup.
