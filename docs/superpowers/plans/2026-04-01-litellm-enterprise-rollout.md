# Plan: Đưa LiteLLM Gateway vào hoạt động doanh nghiệp VNPAY

## Trạng thái hiện tại (Done)
- LiteLLM deployed trên K8s (2 replicas, PG, Redis)
- Teleport app registered (litellm.x.vnshop.cloud)
- Models: claude-sonnet-4-6, claude-opus-4-6, claude-haiku-4-5, gpt-4o, o3-pro, v_glm46
- Health check passing, v_glm46 tested OK
- Proposal doc written cho CTO/Tech Leaders

## Phase 1: Foundation (Tuần 1) — Bảo mật & Admin Setup

### 1.1 Trình bày & phê duyệt CTO
- [ ] Present proposal (`litellm-gateway-vnpay-proposal.md`) cho CTO, Tech Leaders
- [ ] Xin phê duyệt budget API keys (Anthropic, OpenAI credits)
- [ ] Xác định danh sách pilot users (5-10 devs)
- [ ] Xác nhận VNPAY GenAI API key dạng long-lived (JWT hiện tại đã expired)

### 1.2 API Keys & Credits
- [ ] Mua/nạp Anthropic API credits (key hiện tại hết credits)
- [ ] Tạo OpenAI API key (nếu cần GPT-4o/o3-pro)
- [ ] Xin VNPAY GenAI API key dạng service account (không phải JWT cá nhân)
- [ ] Update K8s secret `litellm-provider-keys` với keys mới

### 1.3 Team & Key Management (qua LiteLLM Dashboard)
- [ ] Truy cập Dashboard: `https://litellm.x.vnshop.cloud/ui`
- [ ] Tạo Teams:
  - `platform` — GoClaw, CI/CD (RPM: 100)
  - `dev-tools` — Claude Code developers (RPM: 30/user)
  - `products` — Chatbot, AI features (RPM: 50)
  - `research` — PoC, thử nghiệm (RPM: 20)
- [ ] Set budget limits per team (monthly USD cap)
- [ ] Set model access per team (ví dụ: `dev-tools` all models, `products` chỉ Haiku + GLM)
- [ ] Generate virtual keys cho pilot users

### 1.4 Network Policy
- [ ] Tạo NetworkPolicy cho namespace `litellm`:
  - Ingress: chỉ từ nginx-ingress + sdlc-go-prod namespace
  - Egress: chỉ tới api.anthropic.com, api.openai.com, genai.vnpay.vn, DNS
  - Block egress tới mọi domain khác (chống supply chain exfiltration)

## Phase 2: Pilot (Tuần 2-3) — Onboard Developers

### 2.1 Tài liệu developer
- [ ] Viết quick-start guide cho developers:
  - Cài Teleport CLI (`tsh`)
  - Login + proxy setup (1 lệnh)
  - Cấu hình Claude Code / IDE
  - Cấu hình OpenAI SDK (Python/Node)
- [ ] Tạo script setup tự động (`setup-litellm.sh`):
  ```bash
  #!/bin/bash
  export TELEPORT_PROXY=teleport.x.vnshop.cloud:443
  tsh login --proxy=teleport.x.vnshop.cloud --user=$USER@vnpay.vn
  tsh app login litellm
  tsh proxy app litellm -p 14000 &
  export ANTHROPIC_BASE_URL="http://127.0.0.1:14000"
  echo "LiteLLM ready at http://127.0.0.1:14000"
  ```

### 2.2 Onboard pilot users
- [ ] Cấp virtual key cho 5-10 developers
- [ ] Hướng dẫn 1:1 hoặc workshop 30 phút
- [ ] Thu thập feedback sau 1 tuần sử dụng
- [ ] Monitor usage qua Dashboard (chi phí, model usage, error rates)

### 2.3 Guardrails configuration
- [ ] Cấu hình PII masking (hiện lỗi vì thiếu Presidio — cần deploy Presidio Analyzer/Anonymizer hoặc dùng LiteLLM built-in regex)
- [ ] Enable prompt injection detection
- [ ] Test guardrails với sample data nhạy cảm
- [ ] Tạo custom VNPAY policy (chặn dữ liệu tài chính chưa public)

## Phase 3: Integration (Tuần 3-4) — Migrate Services

### 3.1 Migrate GoClaw
- [ ] Tạo virtual key cho team `platform` (GoClaw service key)
- [ ] Update `goclaw.yaml`: ANTHROPIC_BASE_URL -> `http://litellm.litellm.svc.cluster.local:4000`
- [ ] Update `goclaw-secrets`: anthropic-api-key -> LiteLLM virtual key
- [ ] Update `goclaw.yaml` configmap: provider `cli-proxy-api` -> `anthropic`
- [ ] Deploy updated sdlc-go chart
- [ ] Monitor GoClaw qua LiteLLM Dashboard 48 giờ
- [ ] Disable cli-proxy-api (`cliProxyApi.enabled: false`)
- [ ] Remove cliproxy từ ingress + teleport apps

### 3.2 Integrate Antigravity & hệ thống khác
- [ ] Cấp virtual key per service
- [ ] Cung cấp endpoint + key cho team Antigravity
- [ ] Hỗ trợ integration (OpenAI SDK compatible)

## Phase 4: Production Hardening (Tháng 2) — Scale & Monitor

### 4.1 Monitoring & Alerting
- [ ] Tạo Grafana dashboard cho LiteLLM:
  - Request rate per model, per team
  - Cost per team per day/week/month
  - Error rate + latency P50/P95/P99
  - Token usage trends
- [ ] Setup alerts:
  - Budget > 80% monthly cap -> Slack notification
  - Error rate > 5% -> PagerDuty/Telegram
  - Latency P99 > 10s -> warning

### 4.2 Backup & Recovery
- [ ] Setup PG backup CronJob (daily pg_dump to S3)
- [ ] Test restore procedure
- [ ] Document disaster recovery runbook

### 4.3 Auto-scaling
- [ ] Enable HPA trong LiteLLM values:
  ```yaml
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 5
    targetCPUUtilizationPercentage: 70
  ```
- [ ] Evaluate cluster capacity — có thể cần thêm worker nodes

### 4.4 Public endpoint + Device Pairing (nếu approved)
- [ ] Tạo public floating IP + domain `api.ai.vnpay.vn`
- [ ] Implement device pairing flow (email OTP -> virtual key)
- [ ] Setup WAF/rate limiting trên public endpoint
- [ ] Migrate users từ Teleport sang direct access

## Phase 5: Scale (Tháng 3+) — Toàn công ty

### 5.1 Self-service portal
- [ ] Developer tự đăng ký qua LiteLLM Dashboard
- [ ] SSO integration (VNPAY Active Directory)
- [ ] Auto-provisioning teams theo phòng ban

### 5.2 Thêm providers
- [ ] Gemini (Google Vertex AI)
- [ ] DeepSeek (nếu cần R1 reasoning)
- [ ] Ollama on-premise (cho dữ liệu nhạy cảm tuyệt mật)

### 5.3 Cost optimization
- [ ] Phân tích usage patterns -> recommend model routing
- [ ] Implement smart routing (task đơn giản -> model rẻ)
- [ ] Semantic caching (tái sử dụng response cho câu hỏi tương tự)

## Checklist trước mỗi Phase

| Kiểm tra | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|----------|---------|---------|---------|---------|
| IOC scan (supply chain) | x | x | x | x |
| Backup PG | | x | x | x |
| Load test | | | x | x |
| Security review | x | | x | x |
| CTO approval | x | | | x |
