# LiteLLM K8s Deployment on VNPayCloud

## Context

VNPAY needs a centralized LLM Gateway to serve multiple internal consumers: GoClaw (replacing cli-proxy-api), Claude Code for developers, Antigravity, and other internal systems. LiteLLM provides a unified proxy supporting 100+ LLM providers with built-in key management, cost tracking, and rate limiting.

**Deployment target**: K8s cluster `sdlc-go-k8s-v2` on VNPayCloud, namespace `litellm`.
**Access**: Via Teleport at `teleport.x.vnshop.cloud` (user: duhd@vnpay.vn).

## Approach: Hybrid (Upstream Chart + Custom Infra)

Two Helm releases in namespace `litellm`:

1. **`litellm-infra`** (custom chart): PostgreSQL StatefulSet + Redis Deployment + SealedSecrets -- following sdlc-go operational patterns.
2. **`litellm`** (upstream chart v1.1.0 from `deploy/charts/litellm-helm/`): LiteLLM application, Prisma migration job, Ingress, PDB.

### Why this approach
- Upstream chart maintains LiteLLM app concerns (migration jobs, probes, PDB)
- DB/Redis follow sdlc-go patterns (same debugging, same SealedSecrets flow)
- LiteLLM can be upgraded independently of infrastructure
- Clean namespace isolation from sdlc-go workloads

## Architecture

```
Namespace: litellm
+-------------------------------------------------------------+
|  Helm Release: litellm-infra (custom)                       |
|  +-----------------------+  +--------------------+          |
|  | PostgreSQL StatefulSet|  | Redis Deployment   |          |
|  | postgres:16-alpine    |  | redis:7-alpine     |          |
|  | Port: 5432            |  | Port: 6379         |          |
|  | PVC: 5Gi (c1-standard)|  | maxmemory: 128MB   |          |
|  +-----------------------+  +--------------------+          |
|  SealedSecrets: litellm-postgres-credentials,               |
|                 litellm-master-key,                         |
|                 litellm-provider-keys                       |
+-------------------------------------------------------------+
|  Helm Release: litellm (upstream chart)                     |
|  +--------------------------------------------------+      |
|  | LiteLLM Deployment (2 replicas)                   |      |
|  | Image: ghcr.io/berriai/litellm-database           |      |
|  | Port: 4000                                        |      |
|  | Env: DATABASE_URL, LITELLM_MASTER_KEY,            |      |
|  |      LITELLM_SALT_KEY, provider API keys          |      |
|  +--------------------------------------------------+      |
|  | Prisma Migration Job (pre-install/upgrade hook)   |      |
|  | ConfigMap (model_list + litellm_settings)         |      |
|  | Service (ClusterIP :4000)                         |      |
|  | Ingress (litellm.x.vnshop.cloud)                  |      |
|  | PodDisruptionBudget (minAvailable: 1)             |      |
+-------------------------------------------------------------+
```

### Traffic Flow

```
Internal (GoClaw, sdlc-go-prod):
  goclaw -> http://litellm.litellm.svc.cluster.local:4000

External (Claude Code, Antigravity, other systems):
  Client -> tsh proxy app litellm
         -> Teleport App Service (litellm.x.vnshop.cloud)
         -> NGINX Ingress (NodePort 30080 -> LB VIP 10.10.1.87)
         -> litellm Service :4000
         -> LiteLLM Pods
```

## Resource Sizing

| Component | Replicas | CPU Req | CPU Limit | Mem Req | Mem Limit | Storage |
|-----------|----------|---------|-----------|---------|-----------|---------|
| LiteLLM | 2 | 1 | 2 | 2Gi | 4Gi | - |
| PostgreSQL | 1 | 250m | 1 | 256Mi | 1Gi | 5Gi PVC |
| Redis | 1 | 50m | 250m | 64Mi | 192Mi | - |
| **Total** | | **2.3** | | **4.6Gi** | | **5Gi** |

**Cluster impact**: Current usage ~6.0 CPU / ~3.7Gi. After LiteLLM: ~8.3 CPU / ~8.3Gi out of 12 CPU / 24Gi total. Comfortable headroom.

## Helm Release 1: litellm-infra (Custom Chart)

### Chart structure

```
helm/litellm-infra/
  Chart.yaml          # v0.1.0
  values.yaml
  templates/
    namespace.yaml                    # namespace: litellm
    stateful/postgresql.yaml          # PostgreSQL StatefulSet (sdlc-go pattern)
    deployments/redis.yaml            # Redis Deployment (sdlc-go pattern)
    secrets/postgres-credentials.yaml # SealedSecret placeholder
    secrets/litellm-master-key.yaml   # SealedSecret placeholder
    secrets/litellm-provider-keys.yaml # SealedSecret placeholder
```

### PostgreSQL StatefulSet

Following `helm/sdlc-go/templates/stateful/postgresql.yaml` pattern:

- Image: `postgres:16-alpine`
- Database: `litellm`
- User: `litellm`
- Storage: 5Gi, storageClass from values (default: cluster default or `c1-standard`)
- Health check: `pg_isready -U litellm`
- Resources: 256Mi/250m request, 1Gi/1 limit
- Credentials from SealedSecret `litellm-postgres-credentials`

### Redis Deployment

Following `helm/sdlc-go/templates/deployments/redis.yaml` pattern:

- Image: `redis:7-alpine`
- maxmemory: 128MB, allkeys-lru eviction
- Persistence: disabled (`--save ""`)
- Auth: password from SealedSecret `litellm-provider-keys` (REDIS_PASSWORD key)
- Resources: 64Mi/50m request, 192Mi/250m limit
- Health check: `redis-cli -a $REDIS_PASSWORD ping`

### SealedSecrets

3 secrets to create via `kubeseal`:

**litellm-postgres-credentials:**
```
username: litellm
password: <generated>
dsn: postgresql://litellm:<password>@litellm-postgresql:5432/litellm
```

**litellm-master-key:**
```
PROXY_MASTER_KEY: sk-litellm-<generated-uuid>
LITELLM_SALT_KEY: <generated-32-char-string>
```

**litellm-provider-keys:**
```
ANTHROPIC_API_KEY: <anthropic-key>
OPENAI_API_KEY: <openai-key>
REDIS_PASSWORD: <generated>
# Additional providers added later via UI or secret update
```

## Helm Release 2: litellm (Upstream Chart)

### Key values overrides (values-vnpay.yaml)

```yaml
replicaCount: 2
numWorkers: 2

image:
  repository: ghcr.io/berriai/litellm-database
  tag: "main-v1.80.12"  # pin to stable version
  pullPolicy: IfNotPresent

# Disable built-in DB -- using litellm-infra's PostgreSQL
db:
  useExisting: true
  deployStandalone: false
  endpoint: litellm-postgresql
  database: litellm
  url: "postgresql://$(DATABASE_USERNAME):$(DATABASE_PASSWORD)@$(DATABASE_HOST)/$(DATABASE_NAME)"
  secret:
    name: litellm-postgres-credentials
    usernameKey: username
    passwordKey: password

# Disable built-in Redis -- using litellm-infra's Redis
redis:
  enabled: false

# Secrets injection
masterkeySecretName: litellm-master-key
masterkeySecretKey: PROXY_MASTER_KEY
environmentSecrets:
  - litellm-provider-keys

# LiteLLM proxy config
proxy_config:
  model_list:
    # Anthropic models
    - model_name: claude-sonnet-4-6
      litellm_params:
        model: anthropic/claude-sonnet-4-6-20250514
        api_key: os.environ/ANTHROPIC_API_KEY
    - model_name: claude-opus-4-6
      litellm_params:
        model: anthropic/claude-opus-4-6-20250514
        api_key: os.environ/ANTHROPIC_API_KEY
    - model_name: claude-haiku-4-5-20251001
      litellm_params:
        model: anthropic/claude-haiku-4-5-20251001
        api_key: os.environ/ANTHROPIC_API_KEY
    # Claude Code default model names
    - model_name: claude-sonnet-4-5-20250929
      litellm_params:
        model: anthropic/claude-sonnet-4-5-20250929
        api_key: os.environ/ANTHROPIC_API_KEY
    - model_name: claude-opus-4-5-20251101
      litellm_params:
        model: anthropic/claude-opus-4-5-20251101
        api_key: os.environ/ANTHROPIC_API_KEY

    # OpenAI models
    - model_name: gpt-4o
      litellm_params:
        model: openai/gpt-4o
        api_key: os.environ/OPENAI_API_KEY
    - model_name: o3-pro
      litellm_params:
        model: openai/o3-pro
        api_key: os.environ/OPENAI_API_KEY

  general_settings:
    master_key: os.environ/PROXY_MASTER_KEY
    store_model_in_db: true  # allow adding models via UI

  litellm_settings:
    cache: true
    cache_params:
      type: redis
      host: litellm-redis
      port: 6379
      password: os.environ/REDIS_PASSWORD

# Resources
resources:
  requests:
    cpu: "1"
    memory: 2Gi
  limits:
    cpu: "2"
    memory: 4Gi

# Ingress
ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
  hosts:
    - host: litellm.x.vnshop.cloud
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: tls-vnshop-cloud
      hosts:
        - litellm.x.vnshop.cloud

# Migration job
migrationJob:
  enabled: true
  hooks:
    argocd:
      enabled: false
    helm:
      enabled: true

# PDB
pdb:
  enabled: true
  minAvailable: 1

# Rolling update (zero-downtime)
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1

# Service
service:
  type: ClusterIP
  port: 4000
```

## Teleport App Service Registration

Add to `helm/teleport-agent/values.yaml` in the apps list:

```yaml
- name: litellm
  uri: https://10.101.60.234
  public_addr: litellm.x.vnshop.cloud
  insecure_skip_verify: true
  labels:
    app_label: litellm
  rewrite:
    headers:
      - "Host: litellm.x.vnshop.cloud"
```

## Ingress Update

Add to `helm/sdlc-go/templates/ingress.yaml` (or create separate ingress in litellm namespace):

```yaml
- host: litellm.x.vnshop.cloud
  http:
    paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: litellm
            port:
              number: 4000
```

Note: Since LiteLLM is in its own namespace, the Ingress resource must be in the `litellm` namespace (handled by the upstream chart's ingress template). The TLS secret `tls-vnshop-cloud` must be copied or mirrored to the `litellm` namespace.

## Key/Team Management Strategy

LiteLLM has built-in multi-tenant key management (enabled by `store_model_in_db: true`).

### Teams

| Team | Purpose | RPM Limit | Model Access | Key Type |
|------|---------|-----------|--------------|----------|
| goclaw | GoClaw service | 100 | claude-sonnet-4-6, claude-opus-4-6 | 1 service key |
| claude-code | Developer Claude Code | 30/user | All models | Individual keys per dev |
| antigravity | Antigravity service | 50 | Configured per need | 1 service key |
| internal | Other internal tools | 20 | All models | Shared key |

### Budget Controls (via LiteLLM Dashboard)

- Per-team monthly budget limits (USD)
- Per-key rate limits (RPM, TPM)
- Model-level access control per team
- Usage tracking and reporting

### Credential Flow

```
Provider API keys (Anthropic, OpenAI, etc.)
  -> SealedSecret (litellm-provider-keys)
  -> env vars in LiteLLM pods

LiteLLM master key
  -> SealedSecret (litellm-master-key)
  -> used by admin only

Team virtual keys
  -> Generated via LiteLLM API/UI
  -> Stored in LiteLLM's PostgreSQL
  -> Distributed to consumers (GoClaw env var, dev .env files)
```

## Migration from cli-proxy-api

### Phase 1: Deploy LiteLLM (Day 1)

1. Create namespace `litellm`
2. Copy TLS secret:
   ```bash
   kubectl get secret tls-vnshop-cloud -n sdlc-go-prod -o yaml | \
     sed 's/namespace: .*/namespace: litellm/' | kubectl apply -f -
   ```
3. Create SealedSecrets (3 secrets via kubeseal)
4. Deploy `litellm-infra` chart:
   ```bash
   helm install litellm-infra ./helm/litellm-infra -n litellm
   ```
5. Wait for PG ready, then deploy `litellm` chart:
   ```bash
   helm install litellm ./litellm/deploy/charts/litellm-helm \
     -f values-vnpay.yaml -n litellm
   ```
6. Verify:
   ```bash
   curl -H "Authorization: Bearer $MASTER_KEY" \
     https://litellm.x.vnshop.cloud/health/readiness
   ```

### Phase 2: Teleport Registration (Day 1)

1. Add litellm app entry to teleport-agent values
2. Upgrade teleport-agent Helm release
3. Verify browser access: `https://litellm.x.vnshop.cloud`

### Phase 3: Key Setup (Day 1-2)

1. Access LiteLLM Dashboard via Teleport
2. Create teams: goclaw, claude-code, antigravity, internal
3. Generate virtual keys per team
4. Test Claude Code locally:
   ```bash
   export ANTHROPIC_BASE_URL="https://litellm.x.vnshop.cloud"
   export ANTHROPIC_AUTH_TOKEN="sk-litellm-<virtual-key>"
   claude
   ```

### Phase 4: GoClaw Cutover (Day 2-3)

1. Update sdlc-go Helm values:
   - `ANTHROPIC_BASE_URL`: `http://cli-proxy-api:8317` -> `http://litellm.litellm.svc.cluster.local:4000`
   - `ANTHROPIC_API_KEY`: cli-proxy-api key -> LiteLLM goclaw virtual key
2. Deploy updated sdlc-go chart
3. Monitor GoClaw logs for successful LLM calls through LiteLLM

### Phase 5: Cleanup (Day 3-5)

1. Set `cliProxyApi.enabled: false` in sdlc-go values
2. Remove `cliproxy.x.vnshop.cloud` from:
   - sdlc-go ingress hosts
   - teleport-agent apps
3. Delete cli-proxy-api PVC (`proxy-auths`)
4. Deploy updated charts

## Claude Code Configuration (for developers)

Developers connect Claude Code to LiteLLM via Teleport:

```bash
# 1. Login to Teleport
tsh login --proxy=teleport.x.vnshop.cloud --user=<username>@vnpay.vn

# 2. Set environment variables
export ANTHROPIC_BASE_URL="https://litellm.x.vnshop.cloud"
export ANTHROPIC_AUTH_TOKEN="sk-litellm-<your-virtual-key>"

# 3. Use Claude Code
claude --model claude-sonnet-4-6

# Or set default models
export ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-4-6
export ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-4-5-20251001
claude
```

## Verification Plan

### Post-deployment checks

1. **Health**: `curl https://litellm.x.vnshop.cloud/health/readiness` returns 200
2. **Models**: `curl -H "Authorization: Bearer $KEY" https://litellm.x.vnshop.cloud/v1/models` lists configured models
3. **Chat test**: Send a test chat completion request via curl
4. **UI**: Access dashboard at `https://litellm.x.vnshop.cloud/ui` via Teleport browser
5. **GoClaw**: Trigger a GoClaw agent action and verify it completes via LiteLLM (check LiteLLM logs for request)
6. **Claude Code**: Run `claude --model claude-sonnet-4-6` with LiteLLM base URL, verify responses
7. **Cross-namespace DNS**: From a pod in sdlc-go-prod, verify `nslookup litellm.litellm.svc.cluster.local` resolves

### Monitoring

- LiteLLM logs: `kubectl logs -n litellm -l app=litellm -f`
- Usage dashboard: `https://litellm.x.vnshop.cloud/ui` (cost tracking per team/key)
- Future: enable ServiceMonitor for Prometheus/Grafana integration

## Critical Files

| File | Purpose |
|------|---------|
| `litellm/deploy/charts/litellm-helm/values.yaml` | Upstream chart values reference |
| `helm/sdlc-go/templates/deployments/goclaw.yaml` | GoClaw ANTHROPIC_BASE_URL (line ~272) |
| `helm/sdlc-go/templates/configmaps/goclaw.yaml` | GoClaw provider config |
| `helm/sdlc-go/templates/stateful/postgresql.yaml` | PG pattern reference |
| `helm/sdlc-go/templates/deployments/redis.yaml` | Redis pattern reference |
| `helm/teleport-agent/values.yaml` | Teleport app registration |
| `helm/sdlc-go/templates/ingress.yaml` | Ingress pattern reference |
