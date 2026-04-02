# LiteLLM Gateway - Unified AI Platform cho VNPAY

> **Tài liệu nội bộ** | Ngày: 02/04/2026 | Người trình bày: DuHD - AI Platform Team
> **Đối tượng**: CTO, Tech Leaders, Engineering Managers

---

## 1. Vấn đề hiện tại

Các đội phát triển tại VNPAY đang sử dụng AI/LLM một cách phân tán:

- Mỗi developer tự quản lý API key riêng (Anthropic, OpenAI, Google...)
- Không kiểm soát được chi phí sử dụng AI trên toàn công ty
- Không có audit trail - ai dùng gì, bao nhiêu, cho mục đích gì
- Rủi ro bảo mật: API keys nằm rải rác trên máy cá nhân, Slack, .env files
- Không thể enforce policy: giới hạn model nào được dùng, budget bao nhiêu/tháng

## 2. Giải pháp: LiteLLM Gateway

LiteLLM là **Unified LLM Gateway** - một proxy trung tâm kết nối tất cả AI providers qua một endpoint duy nhất, chạy trên hạ tầng K8s nội bộ VNPayCloud.

```
          Consumers (gửi request)
          ========================
     Claude Code      Antigravity      Hệ thống nội bộ
     CLI / VSCode /   (AI Agent)       (Chatbot, QA,
     Xcode                              Automation...)
          |               |               |
          +---------------+---------------+
                          |
                          v
               +--------------------+
               |  LiteLLM Gateway   |
               |  Guardrails        |
               |  Key Management    |
               |  Cost Tracking     |
               +--------------------+
                          |
          +-------+-------+-------+-------+-------+
          |       |       |       |       |       |
          v       v       v       v       v       v
      VNPAY    Anthropic OpenAI  Gemini DeepSeek Ollama
      GenAI    Claude    GPT-4o  Gemini  DeepSeek (On-premise)
      GLM-4    Opus/     o3-pro  2.5     R1       Qwen, Llama
      (v_glm46)Sonnet    Codex   Flash             CodeGemma...
          ========================
          Providers (LLM backends)
```

## 3. Kiến trúc triển khai tại VNPayCloud

```
                    Developer / Service
                          |
                          | HTTPS
                          v
                   VNPayCloud WAF/CDN
               (api-llm.x.vnshop.cloud)
                          |
                          v
                Floating IP: 103.67.184.237
                          |
                          v
+------------------------------------------------------------------+
|                      VNPayCloud K8s Cluster                      |
|                      (sdlc-go-k8s-v2)                            |
|                                                                  |
|            LB VIP: 10.10.1.87 (SG: WAF IPs allowlist)           |
|                          |                                       |
|              NodePort 30080/30443                                |
|                          |                                       |
|              NGINX Ingress Controller                            |
|              ├── api-llm.x.vnshop.cloud  (public, WAF whitelist) |
|              └── litellm.x.vnshop.cloud  (admin, Teleport only)  |
|                          |                                       |
|  +--- Namespace: litellm -----------------------------------+    |
|  |                                                          |    |
|  |  +------------------+    +------------+    +---------+   |    |
|  |  | LiteLLM Gateway  |    | PostgreSQL |    |  Redis  |   |    |
|  |  | (2 replicas, HA) |    | 16-alpine  |    | Cache   |   |    |
|  |  | Port: 4000       |    | Keys, Teams|    | Rate    |   |    |
|  |  |                  |    | Usage Logs |    | Limit   |   |    |
|  |  | - Guardrails     |    +------------+    +---------+   |    |
|  |  | - Key Mgmt       |         5Gi PVC                    |    |
|  |  | - Cost Tracking  |                                    |    |
|  |  | - Model Router   |                                    |    |
|  |  +--------+---------+                                    |    |
|  |           |                                              |    |
|  +-----------|----------------------------------------------+    |
|              |                                                   |
|  +--- Namespace: sdlc-go-prod ---+  +--- Namespace: teleport -+ |
|  | GoClaw, Web Dashboard,       |  | Teleport Agent          | |
|  | Serena, GitNexus ...          |  | (SSO + MFA, admin UI)   | |
|  +-------------------------------+  +-------------------------+ |
|                                                                  |
+------------------------------------------------------------------+
       |                    |                         |
       v                    v                         v
   VNPAY GenAI         Anthropic API            Ollama Server
   genai.vnpay.vn      (Cloud)                  (On-premise)
   (GLM-4, on-premise)                          (Future)
```

| Thành phần | Chi tiết |
|------------|----------|
| **Hạ tầng** | K8s cluster `sdlc-go-k8s-v2` trên VNPayCloud (3 worker nodes, 4vCPU/8GB each) |
| **Namespace** | `litellm` - tách biệt hoàn toàn khỏi workload khác |
| **HA** | 2 replicas LiteLLM + PodDisruptionBudget, zero-downtime rolling upgrade |
| **Database** | PostgreSQL 16 riêng (lưu virtual keys, teams, usage logs, model config) |
| **Cache** | Redis (response cache, rate limiting, session state) |
| **Public API** | `api-llm.x.vnshop.cloud` → WAF/CDN → Floating IP `103.67.184.237` → LB → Ingress |
| **Admin UI** | `litellm.x.vnshop.cloud` → Teleport SSO + MFA (admin only) |
| **WAF** | VNPayCloud WAF/CDN (14 WAF IPs whitelist tại NGINX Ingress) |
| **TLS** | Wildcard cert `*.x.vnshop.cloud` (WAF terminate TLS, internal HTTP) |
| **Bảo mật** | WAF IP whitelist, LiteLLM API key auth, SealedSecrets cho provider credentials |
| **Monitoring** | Jaeger (request tracing), Grafana (cost dashboard), Prometheus metrics |
| **Models hiện tại** | `v_glm46` (VNPAY GenAI GLM-4 on-premise) — tested & verified |

**Truy cập hiện tại**: Public endpoint `https://api-llm.x.vnshop.cloud` qua WAF/CDN. Developer chỉ cần API key, không cần VPN hay Teleport. Admin dashboard qua Teleport SSO tại `litellm.x.vnshop.cloud`.

## 4. Lợi ích Enterprise

### Chi phí & Kiểm soát
- **Cost tracking real-time**: Dashboard hiển thị chi phí theo team, dự án, cá nhân
- **Budget limits**: Set ngân sách tối đa/tháng cho mỗi team (alert khi đạt 80%)
- **Rate limiting**: Giới hạn request/phút để tránh chi phí đột biến
- **Một hóa đơn**: Thay vì mỗi dev tự mua credits riêng

### Bảo mật & Compliance
- **WAF/CDN**: Traffic qua VNPayCloud WAF trước khi tới gateway, chống DDoS và injection
- **API Key Auth**: Mọi request cần virtual key hợp lệ, key có rate limit và budget
- **Audit log**: Ghi nhận mọi request - ai, lúc nào, model nào, bao nhiêu tokens
- **Key rotation**: Thay đổi API key provider mà không ảnh hưởng người dùng (virtual key tách biệt khỏi provider key)
- **Data sovereignty**: Gateway chạy trên VNPayCloud, dữ liệu nhạy cảm route qua VNPAY GenAI on-premise (zero data egress)
- **Guardrails**: PII auto-redaction, prompt injection blocking, data leak prevention - filter tại gateway trước khi data rời infra
- **Admin UI bảo mật**: Dashboard quản trị chỉ truy cập qua Teleport SSO + MFA

### On-premise Models: VNPAY GenAI & Ollama

LiteLLM hỗ trợ kết nối các LLM chạy trực tiếp trên hạ tầng nội bộ VNPAY, **dữ liệu không bao giờ rời khỏi datacenter**:

```
  LiteLLM Gateway
       |
       +---> VNPAY GenAI: genai.vnpay.vn (GLM-4, đã triển khai)
       |
       +---> Cloud: Anthropic, OpenAI, Gemini (khi cần model mạnh)
       |
       +---> Ollama Server (future, mạng nội bộ VNPAY)
              GPU Server / VNPayCloud VM
              ├── qwen2.5-coder:32b    (coding, 32B params)
              ├── llama3.3:70b         (general, 70B params)
              ├── codegemma:7b         (code review, nhẹ)
              └── deepseek-r1:14b      (reasoning)
```

**Cấu hình** - thêm model qua `config.yaml` hoặc Dashboard UI:

```yaml
model_list:
  # VNPAY GenAI Gateway (on-premise, đã triển khai)
  - model_name: v_glm46
    litellm_params:
      model: openai/v_glm46
      api_base: https://genai.vnpay.vn/aigateway/llm_glm46/v1
      api_key: os.environ/VNPAY_GENAI_API_KEY

  # Ollama models (on-premise, future)
  - model_name: qwen-coder-local
    litellm_params:
      model: ollama/qwen2.5-coder:32b
      api_base: http://ollama-server.vnpay.internal:11434
```

**So sánh Cloud vs On-premise:**

| | Cloud Models | On-premise (VNPAY GenAI / Ollama) |
|---|---|---|
| **Chi phí** | Pay-per-token | Hạ tầng sẵn có - chạy unlimited |
| **Dữ liệu** | Gửi ra internet (có Guardrails filter) | 100% nội bộ - zero data egress |
| **Latency** | ~500ms-2s (phụ thuộc provider) | ~100-500ms (mạng nội bộ) |
| **Compliance** | Phụ thuộc DPA với provider | Hoàn toàn kiểm soát |
| **Use case** | Task phức tạp cần model mạnh | Code review, dịch thuật, phân tích log, dữ liệu nhạy cảm |

**Hybrid routing** - LiteLLM tự động route theo policy:
- Dữ liệu nhạy cảm (tài chính, PII) -> route tới **VNPAY GenAI on-premise**
- Task cần model mạnh (kiến trúc, debug phức tạp) -> route tới **Claude/GPT-4o cloud**
- Task đơn giản (format code, tóm tắt) -> route tới **on-premise** (tiết kiệm chi phí)

### AI Security Guardrails

LiteLLM tích hợp lớp bảo vệ **Guardrails** - kiểm soát nội dung đầu vào/đầu ra trước khi gửi tới LLM provider, đảm bảo an toàn dữ liệu doanh nghiệp:

```
  Developer / App                      LLM Provider
       |                                    ^
       v                                    |
  +-----------+    +----------------+    +--+--+
  |  Request  |--->|  GUARDRAILS    |--->|  AI |
  |           |    |                |    |Model|
  |  Response |<---|  - PII Redact  |<---|     |
  +-----------+    |  - Injection   |    +-----+
                   |  - Toxic Filter|
                   |  - Data Leak   |
                   |  - Custom Rule |
                   +----------------+
                   (chạy trên infra VNPAY)
```

| Guardrail | Chức năng | Ví dụ |
|-----------|-----------|-------|
| **Prompt Injection Blocking** | Phát hiện và chặn prompt injection attacks trong input | Chặn khi user cố gắng bypass system prompt, jailbreak model, hoặc inject lệnh độc hại qua input |
| **PII Auto-Redaction** | Tự động che/xóa thông tin cá nhân (CCCD, SĐT, STK, email) trước khi gửi ra ngoài | `"Khách hàng Nguyễn Văn A, SĐT 0901234567"` -> `"Khách hàng [REDACTED], SĐT [REDACTED]"` - dữ liệu nhạy cảm không bao giờ rời khỏi infra VNPAY |
| **Toxic Response Filtering** | Lọc nội dung độc hại, không phù hợp trong response từ LLM | Chặn output chứa nội dung bạo lực, phân biệt, hoặc không phù hợp với quy chuẩn doanh nghiệp |
| **Data Leak Prevention** | Ngăn rò rỉ dữ liệu nội bộ (API keys, credentials, schema DB, source code nhạy cảm) | Phát hiện và chặn khi prompt chứa connection strings, private keys, hoặc nội dung classified |
| **Custom Policy Engine** | Tạo rules riêng theo chính sách VNPAY | Ví dụ: chặn mọi request liên quan đến dữ liệu tài chính chưa public, giới hạn model nào được dùng cho dữ liệu nào, enforce tiếng Việt trong output |

**Điểm mấu chốt**: Toàn bộ Guardrails xử lý **tại gateway trên VNPayCloud** - dữ liệu nhạy cảm được filter trước khi gửi tới Anthropic/OpenAI. Không phụ thuộc vào trust boundary của provider bên ngoài.

Cấu hình Guardrails qua `config.yaml` hoặc LiteLLM Dashboard, không cần thay đổi code phía client:

```yaml
# Ví dụ config guardrails
litellm_settings:
  guardrails:
    - prompt_injection:        # Chặn prompt injection
        callbacks: [lakera_prompt_injection]
        default_on: true
    - pii_masking:             # Che thông tin cá nhân
        callbacks: [presidio]
        default_on: true
    - content_moderation:      # Lọc nội dung độc hại
        callbacks: [openai_moderation]
        default_on: true
    - custom_vnpay_policy:     # Policy riêng VNPAY
        callbacks: [custom_guardrail]
        default_on: true
```

### Supply Chain Security - Bài học từ sự cố 24/03/2026

> **Context**: Ngày 24/03/2026, hacker nhóm **TeamPCP** đã upload 2 phiên bản độc hại (v1.82.7, v1.82.8) lên PyPI thông qua token bị đánh cắp từ CI/CD pipeline. Payload thu thập API keys, SSH keys, K8s tokens, cloud credentials và gửi về server của attacker. Phiên bản độc hại tồn tại ~3 giờ trước khi bị gỡ. Deployment VNPAY dùng v1.82.3 - **KHÔNG bị ảnh hưởng**.

Các biện pháp đã áp dụng để hạn chế rủi ro:

| Biện pháp | Chi tiết |
|-----------|----------|
| **Pin image digest** | Image K8s pin theo SHA256 digest cụ thể, không dùng mutable tag (`main-latest`, `main-stable`) |
| **Không dùng PyPI trực tiếp** | Deploy qua Docker image (ghcr.io), không `pip install` runtime - tránh bị ảnh hưởng bởi PyPI compromise |
| **IOC scan trước upgrade** | Trước mỗi lần upgrade, kiểm tra: không có file `.pth` lạ, không có domain `models.litellm.cloud` / `checkmarx.zone` |
| **Secrets isolation** | Provider API keys nằm trong K8s SealedSecrets, developer chỉ nhận virtual key - nếu gateway bị compromise, key gốc không bị lộ |
| **Network policy** | LiteLLM pods chỉ được gọi ra Anthropic/OpenAI API endpoints, không gọi được domain lạ |
| **Upgrade quy trình** | Mọi upgrade phải qua review: check release notes -> verify image -> scan IOCs -> deploy staging -> deploy prod |

### Linh hoạt & Tối ưu
- **Multi-provider**: Chuyển đổi giữa VNPAY GenAI/Anthropic/OpenAI/Gemini không cần đổi code
- **Fallback tự động**: Model A lỗi -> tự động chuyển sang Model B
- **Load balancing**: Phân tải request qua nhiều API keys cùng provider
- **Model routing**: Dùng model on-premise cho task thường, model cloud cho task phức tạp

## 5. Hướng dẫn sử dụng

### 5.1 Claude Code CLI (Terminal)

Claude Code CLI là coding assistant chạy trực tiếp trong terminal - đọc/sửa code, chạy tests, tạo PR, debug, refactor codebase lớn. Hỗ trợ context 1 triệu tokens.

**Cấu hình (chỉ cần làm 1 lần):**

```bash
# Set environment variables (thêm vào ~/.bashrc hoặc ~/.zshrc)
export ANTHROPIC_BASE_URL="https://api-llm.x.vnshop.cloud"
export ANTHROPIC_AUTH_TOKEN="<virtual-key-được-cấp>"
```

**Sử dụng:**

```bash
claude                           # Mở Claude Code
claude --model v_glm46           # Dùng VNPAY GLM-4 on-premise
claude --model claude-sonnet-4-6 # Dùng Claude Sonnet (khi có Anthropic credits)
```

### 5.2 Claude Code trong VS Code

Claude Code tích hợp trực tiếp vào VS Code qua extension, hoạt động như AI pair-programmer ngay trong IDE.

**Cài đặt:**

1. VS Code → Extensions → Tìm **"Claude Code"** → Install
2. Mở Settings (Ctrl+,) → tìm "claude" → cấu hình:

```json
// VS Code settings.json
{
  "claude-code.anthropicBaseUrl": "https://api-llm.x.vnshop.cloud",
  "claude-code.anthropicAuthToken": "<virtual-key-được-cấp>"
}
```

Hoặc cấu hình qua environment variables (tự động nhận từ terminal):

```bash
# Thêm vào ~/.bashrc hoặc ~/.zshrc (dùng chung với CLI)
export ANTHROPIC_BASE_URL="https://api-llm.x.vnshop.cloud"
export ANTHROPIC_AUTH_TOKEN="<virtual-key-được-cấp>"
```

**Tính năng trong VS Code:**
- Chat panel tích hợp bên phải IDE
- Chọn code → right-click → "Ask Claude" để hỏi về đoạn code
- Inline code suggestions và auto-complete
- Đọc toàn bộ workspace context (files, git history, terminal output)
- Chạy commands, edit files, tạo PR trực tiếp từ chat

### 5.3 Claude Code trong Xcode (macOS Apple Silicon)

Xcode 26.3+ tích hợp Claude Code native. Kết nối qua LiteLLM Gateway với vài bước:

**Yêu cầu:** macOS 26.2+, Xcode 26.3+, Mac Apple Silicon (M1/M2/M3/M4)

**Bước 1: Cài Claude Code component**

Xcode → Settings → Intelligence → Anthropic → Claude Agent → **Get**

**Bước 2: Bypass authentication mặc định**

```bash
defaults write com.apple.dt.Xcode IDEChatClaudeAgentAPIKeyOverride ' '
```

**Bước 3: Cấu hình endpoint LiteLLM**

```bash
mkdir -p ~/Library/Developer/Xcode/CodingAssistant/ClaudeAgentConfig
```

Tạo file `~/Library/Developer/Xcode/CodingAssistant/ClaudeAgentConfig/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<virtual-key-được-cấp>",
    "ANTHROPIC_BASE_URL": "https://api-llm.x.vnshop.cloud"
  }
}
```

**Bước 4:** Restart Xcode

**Troubleshooting:** Logs tại `~/Library/Developer/Xcode/CodingAssistant/ClaudeAgentConfig/debug/`

> Ref: https://gist.github.com/zoltan-magyar/be846eb36cf5ee33c882ef5f932b754b

### 5.4 Antigravity & hệ thống nội bộ

Antigravity và các AI agent/service kết nối LiteLLM qua OpenAI-compatible API:

```
Base URL:  https://api-llm.x.vnshop.cloud      (public qua WAF)
API Key:   <virtual-key-được-cấp-cho-service>
```

**Từ K8s pods** (bypass WAF, gọi thẳng Floating IP):
```
Base URL:  http://api-llm.x.vnshop.cloud       (HTTP qua Floating IP)
hostAlias: 103.67.184.237 api-llm.x.vnshop.cloud
```

Hỗ trợ chuẩn OpenAI API (`/v1/chat/completions`) và Anthropic API (`/v1/messages`), tương thích mọi SDK/framework hiện có.

### 5.5 OpenAI SDK / Python / Node.js

Sử dụng bất kỳ model nào qua cùng gateway - không cần API key riêng từng provider:

```bash
# Environment variables
export OPENAI_BASE_URL="https://api-llm.x.vnshop.cloud/v1"
export OPENAI_API_KEY="<virtual-key-được-cấp>"
```

```python
# Python
from openai import OpenAI
client = OpenAI(base_url="https://api-llm.x.vnshop.cloud/v1", api_key="<key>")
response = client.chat.completions.create(
    model="v_glm46",
    messages=[{"role": "user", "content": "Phân tích kiến trúc microservice"}]
)
```

### 5.6 Tổng hợp endpoints

| Endpoint | Mục đích | Truy cập |
|----------|----------|----------|
| `https://api-llm.x.vnshop.cloud` | API cho Claude Code, SDK, services | Public qua WAF, chỉ cần API key |
| `https://litellm.x.vnshop.cloud` | Dashboard UI quản trị | Qua Teleport SSO (admin only) |
| `http://api-llm.x.vnshop.cloud` | K8s services nội bộ | Qua Floating IP + hostAlias (bypass WAF) |

## 6. Mô hình quản lý Team & Key

| Team | Mục đích | Models | Budget/tháng |
|------|----------|--------|--------------|
| **platform** | GoClaw, CI/CD automation | v_glm46, Claude Sonnet | Theo dự án |
| **dev-tools** | Claude Code cho developers | All models | Theo headcount |
| **products** | Chatbot, AI features | v_glm46, Haiku | Theo sản phẩm |
| **research** | Nghiên cứu, PoC | All models | Cố định |

Mỗi developer/service nhận **virtual key** riêng. Admin quản lý qua **LiteLLM Dashboard** (web UI) tại `litellm.x.vnshop.cloud/ui` - truy cập qua Teleport SSO.

## 7. Roadmap

| Phase | Thời gian | Nội dung | Status |
|-------|-----------|----------|--------|
| **Phase 1** | Tuần 1 | Deploy LiteLLM Gateway, public endpoint qua WAF | **Done** |
| **Phase 2** | Tuần 2 | Onboard 5-10 developers, setup teams & budgets | In progress |
| **Phase 3** | Tuần 3-4 | Migrate GoClaw sang LiteLLM, thêm Anthropic/OpenAI credits | Planned |
| **Phase 4** | Tháng 2 | Grafana cost dashboard, Guardrails config, backup | Planned |
| **Phase 5** | Tháng 2-3 | Onboard toàn công ty, self-service portal | Planned |
| **Phase 6** | Tháng 3+ | SSO integration (VNPAY AD), device pairing, Ollama on-premise | Planned |

## 8. Chi phí ước tính

| Khoản mục | Chi phí |
|-----------|---------|
| **Hạ tầng** (K8s, VNPayCloud) | Dùng chung cluster hiện tại - không phát sinh thêm |
| **LiteLLM** | Open-source, miễn phí |
| **VNPAY GenAI** (v_glm46) | Hạ tầng nội bộ sẵn có - không phát sinh thêm |
| **API Usage** (Anthropic, OpenAI) | Theo usage thực tế, kiểm soát qua budget limits |
| **WAF/CDN + Floating IP** | Chi phí minimal |

**ROI**: Với 20 developers dùng Claude Code, tiết kiệm ước tính **3-5 giờ/dev/tuần** cho coding tasks. Kiểm soát chi phí AI tập trung thay vì phân tán qua nhiều tài khoản cá nhân.

---

**Liên hệ**: DuHD (duhd@vnpay.vn) - AI Platform Team
**Public API**: https://api-llm.x.vnshop.cloud
**Admin Dashboard**: https://litellm.x.vnshop.cloud (qua Teleport SSO)
**Status**: Phase 1 hoàn tất - Gateway đang chạy production, `v_glm46` tested OK
