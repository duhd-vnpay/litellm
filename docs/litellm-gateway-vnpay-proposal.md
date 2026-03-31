# LiteLLM Gateway - Unified AI Platform cho VNPAY

> **Tài liệu nội bộ** | Ngày: 31/03/2026 | Người trình bày: DuHD - AI Platform Team
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
     Claude Code    Antigravity      Hệ thống nội bộ
     (Developer)    (AI Agent)       (Chatbot, QA,
                                      Automation...)
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
      Anthropic OpenAI  Gemini DeepSeek  Groq   Ollama
      Claude    GPT-4o  Gemini  DeepSeek Llama  (On-premise)
      Opus/     o3-pro  2.5     R1       3.3    Qwen, Llama
      Sonnet    Codex   Flash                   CodeGemma...
          ========================
          Providers (LLM backends)
```

## 3. Kiến trúc triển khai tại VNPayCloud

```
+------------------------------------------------------------------+
|                      VNPayCloud K8s Cluster                      |
|                      (sdlc-go-k8s-v2)                            |
|                                                                  |
|  +--- Namespace: litellm -----------------------------------+    |
|  |                                                          |    |
|  |  +------------------+    +------------+    +---------+   |    |
|  |  | LiteLLM Gateway  |    | PostgreSQL |    |  Redis  |   |    |
|  |  | (2 replicas, HA) |--->| 16-alpine  |    | Cache   |   |    |
|  |  | Port: 4000       |    | Keys, Teams|    | Rate    |   |    |
|  |  |                  |--->| Usage Logs |    | Limit   |   |    |
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
|  | Serena, GitNexus ...          |  | (SSO + MFA gateway)     | |
|  +-------------------------------+  +-------------------------+ |
|                                                                  |
+------------------------------------------------------------------+
       |                    |                         |
       v                    v                         v
   Anthropic API       OpenAI API              Ollama Server
   (Cloud)             (Cloud)                 (On-premise)
```

| Thành phần | Chi tiết |
|------------|----------|
| **Hạ tầng** | K8s cluster `sdlc-go-k8s-v2` trên VNPayCloud (3 worker nodes, 4vCPU/8GB each) |
| **Namespace** | `litellm` - tách biệt hoàn toàn khỏi workload khác |
| **HA** | 2 replicas LiteLLM + PodDisruptionBudget, zero-downtime rolling upgrade |
| **Database** | PostgreSQL 16 riêng (lưu virtual keys, teams, usage logs, model config) |
| **Cache** | Redis (response cache, rate limiting, session state) |
| **Ingress** | NGINX Ingress Controller, TLS wildcard `*.x.vnshop.cloud` |
| **Bảo mật** | Teleport Zero Trust (SSO + MFA), SealedSecrets cho credentials, Guardrails |
| **Monitoring** | Jaeger (request tracing), Grafana (cost dashboard), Prometheus metrics |
| **Truy cập Pilot** | Qua Teleport: `litellm.x.vnshop.cloud` (không expose internet) |
| **Truy cập Prod** | Public endpoint + device pairing qua email `@vnpay.vn` |

**Bảo mật giai đoạn Pilot**: Không expose ra internet. Mọi truy cập đều qua **Teleport** (Zero Trust Access) với xác thực SSO VNPAY. API keys provider (Anthropic, OpenAI...) lưu encrypted trong K8s SealedSecrets, developer không bao giờ thấy key gốc - chỉ nhận virtual key có rate limit và budget.

## 4. Lợi ích Enterprise

### Chi phí & Kiểm soát
- **Cost tracking real-time**: Dashboard hiển thị chi phí theo team, dự án, cá nhân
- **Budget limits**: Set ngân sách tối đa/tháng cho mỗi team (alert khi đạt 80%)
- **Rate limiting**: Giới hạn request/phút để tránh chi phí đột biến
- **Một hóa đơn**: Thay vì mỗi dev tự mua credits riêng

### Bảo mật & Compliance
- **Zero Trust (Pilot)**: Truy cập qua Teleport SSO + MFA, không expose public internet
- **Device Pairing (Prod)**: Public endpoint nhưng chỉ chấp nhận paired devices - xác thực qua email `@vnpay.vn`, key bound to device, revoke khi mất thiết bị hoặc nghỉ việc
- **Audit log**: Ghi nhận mọi request - ai, từ device nào, lúc nào, model nào, bao nhiêu tokens
- **Key rotation**: Thay đổi API key provider mà không ảnh hưởng người dùng (virtual key tách biệt khỏi provider key)
- **Data sovereignty**: Gateway chạy trên VNPayCloud, dữ liệu nhạy cảm route qua Ollama on-premise (zero data egress)
- **Guardrails**: PII auto-redaction, prompt injection blocking, data leak prevention - filter tại gateway trước khi data rời infra

### On-premise Models với Ollama

LiteLLM hỗ trợ kết nối **Ollama** - chạy LLM trực tiếp trên server nội bộ VNPAY, **dữ liệu không bao giờ rời khỏi datacenter**:

```
  LiteLLM Gateway
       |
       +---> Cloud: Anthropic, OpenAI, Gemini (qua internet)
       |
       +---> On-premise: Ollama Server (mạng nội bộ VNPAY)
              GPU Server / VNPayCloud VM
              ├── qwen2.5-coder:32b    (coding, 32B params)
              ├── llama3.3:70b         (general, 70B params)
              ├── codegemma:7b         (code review, nhẹ)
              ├── deepseek-r1:14b      (reasoning)
              └── gemma3:27b           (tiếng Việt tốt)
```

**Cấu hình đơn giản** - thêm Ollama vào `config.yaml` hoặc qua Dashboard UI:

```yaml
model_list:
  # On-premise models (Ollama) - data stays in VNPAY
  - model_name: qwen-coder-local
    litellm_params:
      model: ollama/qwen2.5-coder:32b
      api_base: http://ollama-server.vnpay.internal:11434

  - model_name: llama-local
    litellm_params:
      model: ollama/llama3.3:70b
      api_base: http://ollama-server.vnpay.internal:11434
```

**Lợi ích on-premise:**

| | Cloud Models | Ollama On-premise |
|---|---|---|
| **Chi phí** | Pay-per-token | Một lần (GPU server) - chạy unlimited |
| **Dữ liệu** | Gửi ra internet (có Guardrails filter) | 100% nội bộ - zero data egress |
| **Latency** | ~500ms-2s (phụ thuộc provider) | ~100-500ms (mạng LAN) |
| **Compliance** | Phụ thuộc DPA với provider | Hoàn toàn kiểm soát |
| **Use case** | Task phức tạp cần model mạnh | Code review, dịch thuật, phân tích log, dữ liệu nhạy cảm |

**Hybrid routing** - LiteLLM tự động route theo policy:
- Dữ liệu nhạy cảm (tài chính, PII) -> route tới **Ollama on-premise**
- Task cần model mạnh (kiến trúc, debug phức tạp) -> route tới **Claude/GPT-4o cloud**
- Task đơn giản (format code, tóm tắt) -> route tới **Ollama on-premise** (tiết kiệm chi phí)

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

### Linh hoạt & Tối ưu
- **Multi-provider**: Chuyển đổi giữa Anthropic/OpenAI/Gemini không cần đổi code
- **Fallback tự động**: Model A lỗi -> tự động chuyển sang Model B
- **Load balancing**: Phân tải request qua nhiều API keys cùng provider
- **Model routing**: Dùng model rẻ (Haiku) cho task đơn giản, model mạnh (Opus) cho task phức tạp

## 5. Hướng dẫn sử dụng

### 5.1 Claude Code (AI Coding Assistant)

Claude Code là CLI coding assistant của Anthropic - hỗ trợ viết code, debug, review, deploy.

```bash
# Bước 1: Login Teleport (một lần/ngày)
tsh login --proxy=teleport.x.vnshop.cloud --user=<tên>@vnpay.vn

# Bước 2: Mở proxy tới LiteLLM
tsh proxy app litellm -p 14000 &

# Bước 3: Cấu hình Claude Code
export ANTHROPIC_BASE_URL="http://127.0.0.1:14000"
export ANTHROPIC_AUTH_TOKEN="<virtual-key-được-cấp>"

# Bước 4: Sử dụng
claude                           # Mở Claude Code
claude --model claude-opus-4-6   # Dùng model cụ thể
```

**Tính năng nổi bật**: Đọc/sửa code trực tiếp, chạy tests, tạo PR, debug lỗi phức tạp, refactor codebase lớn. Hỗ trợ context 1 triệu tokens (đọc toàn bộ codebase cùng lúc).

### 5.2 Antigravity (AI Agent Platform)

Antigravity và các AI agent platform kết nối LiteLLM qua OpenAI-compatible API:

```
Base URL:  http://litellm.litellm.svc.cluster.local:4000  (trong K8s)
           https://litellm.x.vnshop.cloud                  (qua Teleport)
API Key:   <virtual-key-được-cấp-cho-service>
```

Hỗ trợ chuẩn OpenAI API (`/v1/chat/completions`) và Anthropic API (`/v1/messages`), tương thích mọi SDK/framework hiện có.

### 5.3 ChatGPT & OpenAI Models

Sử dụng GPT-4o, o3-pro qua cùng gateway - không cần API key OpenAI riêng:

```bash
# Từ bất kỳ OpenAI SDK/client nào
export OPENAI_BASE_URL="http://127.0.0.1:14000/v1"
export OPENAI_API_KEY="<virtual-key-được-cấp>"

# Python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:14000/v1", api_key="<key>")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Phân tích kiến trúc microservice"}]
)
```

## 6. Mô hình quản lý Team & Key

| Team | Mục đích | Models | Budget/tháng |
|------|----------|--------|--------------|
| **platform** | GoClaw, CI/CD automation | Claude Sonnet, Opus | Theo dự án |
| **dev-tools** | Claude Code cho developers | All models | Theo headcount |
| **products** | Chatbot, AI features | Haiku, GPT-4o | Theo sản phẩm |
| **research** | Nghiên cứu, PoC | All models | Cố định |

Mỗi developer/service nhận **virtual key** riêng. Admin quản lý qua **LiteLLM Dashboard** (web UI) tại `litellm.x.vnshop.cloud/ui` - không cần SSH hay kubectl.

## 7. Roadmap & Mô hình truy cập theo giai đoạn

### Giai đoạn Pilot (Tuần 1-4): Truy cập qua Teleport

```
Developer laptop                    VNPayCloud K8s
+-------------------+              +---------------------+
| tsh proxy app     |   Teleport   |                     |
| litellm -p 14000  |=============>| LiteLLM Gateway     |
|                   |  (encrypted) | :4000               |
| Claude Code       |              |   -> Anthropic API  |
| Antigravity       |              |   -> OpenAI API     |
+-------------------+              +---------------------+
     Mạng nội bộ                      Private network
```

- Truy cập **chỉ qua Teleport** (`tsh login` + `tsh proxy app`)
- Phù hợp nhóm pilot 5-10 developers đã quen Teleport
- Không cần thay đổi infra, bảo mật tối đa
- Mỗi developer cần chạy `tsh proxy app litellm -p 14000` trước khi dùng

| Phase | Thời gian | Nội dung |
|-------|-----------|----------|
| **Phase 1** (Done) | Tuần 1 | Deploy LiteLLM Gateway, test Claude Code |
| **Phase 2** | Tuần 2 | Onboard 5-10 developers pilot qua Teleport, setup teams & budgets |
| **Phase 3** | Tuần 3-4 | Migrate GoClaw sang LiteLLM, thêm OpenAI/Gemini providers |

### Giai đoạn Production (Tháng 2+): Public API Gateway + Device Pairing

```
Developer laptop                         VNPayCloud K8s
+-------------------+                   +---------------------+
|                   |    HTTPS/TLS      |  Public Endpoint    |
| Claude Code       |==================>|  api.ai.vnpay.vn    |
| Antigravity       |  (direct, no VPN) |                     |
| ChatGPT client    |                   |  LiteLLM Gateway    |
+-------------------+                   |  + SSO Auth         |
        |                               |  + Device Pairing   |
        v                               +---------------------+
  Pairing flow:
  1. Dev truy cập api.ai.vnpay.vn/pair
  2. Nhập email @vnpay.vn
  3. Nhận mã xác thực qua email
  4. Nhập mã -> device được pair
  5. Nhận virtual key (bound to device)
```

Khi mở rộng toàn công ty, chuyển sang **public endpoint** để developer không cần Teleport:

**Device Pairing Flow:**

| Bước | Hành động | Chi tiết |
|------|-----------|----------|
| 1 | **Request pairing** | Developer truy cập portal hoặc chạy CLI setup command |
| 2 | **Email verification** | Hệ thống gửi mã OTP tới email `@vnpay.vn` của developer |
| 3 | **Xác thực mã** | Developer nhập mã OTP, device fingerprint được ghi nhận |
| 4 | **Cấp virtual key** | Key được bind với device ID + email, có thời hạn (90 ngày) |
| 5 | **Auto-renewal** | Key tự gia hạn khi device vẫn active, revoke khi device mất/đổi |

**Lợi ích so với Teleport-only:**
- **Không cần VPN/Teleport**: Developer chỉ cần internet, không cần `tsh` CLI
- **Onboarding nhanh**: Tự đăng ký qua email, không cần admin cấp thủ công
- **Device management**: Revoke key khi nhân viên nghỉ việc hoặc mất thiết bị
- **Audit per-device**: Biết chính xác request đến từ thiết bị nào

**Bảo mật production:**
- Endpoint public nhưng **chỉ chấp nhận paired devices** - request không có valid key bị reject
- Virtual key **bound to device** - copy key sang máy khác sẽ không hoạt động
- Rate limiting per-device + per-team budget controls
- Guardrails (PII redaction, prompt injection blocking) vẫn active
- TLS encryption end-to-end

| Phase | Thời gian | Nội dung |
|-------|-----------|----------|
| **Phase 4** | Tháng 2 | Public endpoint `api.ai.vnpay.vn`, device pairing system |
| **Phase 5** | Tháng 2-3 | Onboard toàn công ty, Grafana cost dashboard, self-service portal |
| **Phase 6** | Tháng 3+ | SSO integration (VNPAY AD), auto-provisioning theo phòng ban |

### So sánh hai giai đoạn

| | Pilot (Teleport) | Production (Public + Pairing) |
|---|---|---|
| **Truy cập** | `tsh proxy app` (cần Teleport CLI) | Direct HTTPS (chỉ cần internet) |
| **Onboarding** | Admin cấp key thủ công | Self-service qua email @vnpay.vn |
| **Số user** | 5-10 developers | Toàn công ty (100+) |
| **Setup time** | 5 phút (đã có Teleport) | 2 phút (pair device qua email) |
| **Yêu cầu** | Teleport account + tsh CLI | Email @vnpay.vn + internet |
| **Bảo mật** | Zero Trust (Teleport) | Device-bound keys + TLS + Guardrails |

## 8. Chi phí ước tính

| Khoản mục | Chi phí |
|-----------|---------|
| **Hạ tầng** (K8s, VNPayCloud) | Dùng chung cluster hiện tại - không phát sinh thêm |
| **LiteLLM** | Open-source, miễn phí |
| **API Usage** (Anthropic, OpenAI) | Theo usage thực tế, kiểm soát qua budget limits |
| **Public endpoint** (Phase 4) | Floating IP + domain DNS - chi phí minimal |

**ROI**: Với 20 developers dùng Claude Code, tiết kiệm ước tính **3-5 giờ/dev/tuần** cho coding tasks. Kiểm soát chi phí AI tập trung thay vì phân tán qua nhiều tài khoản cá nhân.

---

**Liên hệ**: Du HD (duhd@vnpay.vn) - AI Platform Team
**Dashboard**: https://litellm.x.vnshop.cloud (qua Teleport SSO)
**Status**: Phase 1 hoàn tất - Gateway đang chạy production trên VNPayCloud
