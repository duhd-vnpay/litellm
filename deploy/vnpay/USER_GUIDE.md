# VNPAY LLM Gateway — User Guide

> **Version 1.4** — cập nhật `2026-04-23` · [Changelog](#changelog)

Hướng dẫn end-user sử dụng LLM Gateway VNPAY: đăng nhập, tạo virtual key, xem usage/logs, và cấu hình các dev tool phổ biến trỏ về gateway.

- **UI Dashboard**: https://litellm.x.vnshop.cloud (Teleport SSO / Google SSO `@vnpay.vn`)
- **API endpoint**: https://api-llm.x.vnshop.cloud
- **Hỗ trợ**: liên hệ team DevOps qua kênh `#litellm-support`

---

## 1. Đăng nhập

### Cách 1 — Teleport (khuyên dùng, internal)

1. Mở Teleport web (hoặc Teleport Connect) đã được cấp tài khoản VNPay.
2. Vào **Applications** → chọn **`litellm`** → click **Launch**.
3. Teleport forward request kèm JWT assertion → LiteLLM tạo session tự động → redirect `/ui/?login=success`.
4. UI hiện dashboard theo role (Admin / Internal User / App User).

### Cách 2 — Google SSO qua oauth2-proxy (fallback)

1. Mở trực tiếp https://litellm.x.vnshop.cloud
2. Redirect sang Google login → **đăng nhập email `@vnpay.vn`**.
3. Chuyển về `/vnpay-sso` → tạo session → vào UI.

Đăng xuất: click avatar góc phải → **Sign Out**, hoặc truy cập `/oauth2/sign_out`.

---

## 2. Danh sách Model có sẵn

| Model alias | Provider thật | Context | Giá (Input/Output per 1M tokens) | Use case |
|---|---|---|---|---|
| `claude-sonnet-4-6` | Anthropic Claude Sonnet 4.6 | 200K | $3 / $15 | Default — coding, analysis, reasoning |
| `claude-sonnet-4-5` | Anthropic Claude Sonnet 4.5 | 200K | $3 / $15 | Coding, analysis |
| `claude-opus-4-6` | Anthropic Claude Opus 4.6 | 200K | $15 / $75 | Deep reasoning, complex tasks |
| `claude-opus-4-5` | Anthropic Claude Opus 4.5 | 200K | $15 / $75 | Deep reasoning |
| `claude-haiku-4-5` | Anthropic Claude Haiku 4.5 | 200K | $1 / $5 | Fast, cheap, small-fast-model |
| `moonshot/kimi-k2.6` | Moonshot Kimi K2.6 (MoE 1T / 32B active) | 256K | $0.95 / $4 (cache hit $0.16) | **Top open-weights** cho agent/coding — Intelligence Index 54 (rank #4, sau Anthropic/Google/OpenAI). Tool use 96% τ²-Bench, hallucination 39% (gần Claude Opus). Thinking mode default |
| `moonshot/kimi-k2.5` | Moonshot Kimi K2.5 | 262K | $0.60 / $3 | Coding/analysis tầm trung, hallucination cao hơn K2.6 |
| `MiniMax-M2.7` | MiniMax M2 cloud | 1M | $0.30 / $1.20 | Cheap long-context, reasoning |
| `vnpay/minimax` | VNPAY GenAI MiniMax on-premise | 131K | **$0** (free) | Dữ liệu nhạy cảm, zero egress |
| `vnpay/v_glm46` | VNPAY GenAI GLM-4 on-premise | 128K | **$0** (free) | Dữ liệu nhạy cảm |
| `vnpay-sensitive` | Alias → `v_glm46` | 128K | $0 | Rõ mục đích: dữ liệu nhạy cảm |
| `vnpay-simple` | Alias → `vnpay/minimax` | 131K | $0 | Tác vụ đơn giản |
| `vnpay-medium` | Alias → `moonshot/kimi-k2.5` | 262K | $0.60 / $3 | Coding mức trung bình |
| `vnpay-smart-routing` | Alias routing tự động | — | varies | Hook tự chọn tier 0/1/2/3 theo prompt |
| `text-embedding-3-small` | BGE-M3 on-premise | 8K | $0 | Embedding 1024 dims, multilingual |

### Chọn model theo tác vụ (quick guide)

- **Agent + coding phức tạp / multi-step** → `moonshot/kimi-k2.6` (rẻ hơn Claude ~3x, agentic gần tương đương frontier) hoặc `claude-sonnet-4-6`
- **Deep reasoning / architecture design** → `claude-opus-4-6` (đắt nhưng không có đối thủ open-weights ngang hàng)
- **Edit đơn giản / format / tóm tắt** → `claude-haiku-4-5` hoặc `vnpay-simple` ($0)
- **Long-context (>256K) rẻ** → `MiniMax-M2.7` (1M ctx, $0.30/$1.20)
- **Dữ liệu nhạy cảm / PII** → `vnpay-sensitive` / `vnpay/minimax` (on-premise, $0, zero egress)
- **Không biết chọn gì** → `vnpay-smart-routing` (hook tự phân tier 0/1/2/3 dựa keyword prompt)

**Benchmark Kimi K2.6** ([Artificial Analysis review](https://artificialanalysis.ai/articles/kimi-k2-6-the-new-leading-open-weights-model)): MoE 1T / 32B active params, Intelligence Index 54 (rank #4 overall, sau Anthropic/Google/OpenAI ở 57). Agentic GDPval-AA Elo 1520 (từ K2.5's 1309 → cải thiện mạnh). Tool use 96% τ²-Bench Telecom. Hallucination rate 39% (giảm từ 65% ở K2.5, gần Claude Opus 4.7's 36%). Reasoning tokens / full eval ~160M (Claude Sonnet 4.6: ~190M, GPT 5.4: ~110M). Hỗ trợ multimodal (image + video input).

> **Lưu ý quan trọng về dữ liệu nhạy cảm**: Mọi prompt chứa PII (CMND, OTP, số thẻ, thông tin khách hàng thực) **phải** dùng `vnpay-sensitive` / `vnpay/v_glm46` / `vnpay/minimax` — chạy on-premise, zero egress. Routing hook cũng tự động redirect sang on-premise khi phát hiện PII keyword.

---

## 3. Tạo Virtual Key

Virtual key là API key cá nhân gắn với user/team — dùng cho mọi tool bên ngoài thay vì chia sẻ master key.

### Tạo qua UI

1. Đăng nhập https://litellm.x.vnshop.cloud
2. Sidebar trái → **Virtual Keys**
3. Click **+ Create New Key**
4. Điền:
   - **Key Alias**: tên gợi nhớ, ví dụ `dungntt-pc`
   - **Team**: chọn team của bạn (nếu có — budget tính theo team)
   - **Models**: tick models được phép (hoặc `all-team-models` cho full access)
   - **Max Budget**: limit USD/key (khuyến nghị $20-50/key, tránh runaway)
   - **Budget Duration**: `monthly` / `weekly` / `daily` / `no-reset`
   - **TPM/RPM limits**: optional — cap rate limit
   - **Expires**: optional — ví dụ `30d`, `90d`
5. Click **Create Key** → **copy key ngay** (dạng `sk-xxxxxxxxx`, chỉ hiện 1 lần).

### Tạo qua CLI (cho CI/CD)

```bash
# Cần master key (xin từ DevOps)
curl -X POST https://api-llm.x.vnshop.cloud/key/generate \
  -H "Authorization: Bearer <MASTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "key_alias": "ci-jenkins-team-dvnh",
    "team_id": "<your-team-uuid>",
    "models": ["claude-sonnet-4-6", "moonshot/kimi-k2.6"],
    "max_budget": 20,
    "budget_duration": "monthly",
    "duration": "90d"
  }'
```

### An toàn khi lưu key

- **KHÔNG** commit key vào git (có pre-commit hook của team chặn, nhưng vẫn cẩn thận)
- Dùng **OS keychain** khi có thể (macOS Keychain, Windows Credential Manager)
- Hoặc export env var trong `~/.zshrc` / `~/.bashrc` (chmod 600)
- Revoke ngay nếu key leak: UI → Virtual Keys → tìm key → **Delete** hoặc **Regenerate**

---

## 4. Xem Usage

### Dashboard Usage tab

1. Sidebar → **Usage**
2. Các filter:
   - **Date range**: 7d / 30d / custom
   - **Group by**: model / team / user / key
   - **Models**: filter cụ thể model(s)
3. Biểu đồ:
   - **Spend over time** — chi tiêu theo ngày
   - **Top models** — model nào dùng nhiều nhất
   - **Top users/keys** — ai tiêu nhiều nhất (admin only)
4. Export CSV: nút **Download** góc phải bảng

### Tab Personal (user thường)

Nếu role = `internal_user` / `app_user`, bạn chỉ thấy usage của chính mình + team. Admin thấy toàn bộ tenant.

### Budget alerts

Khi spend > 80% budget, UI hiện banner warning. Khi > 100%, key tự động block đến kỳ reset kế tiếp.

---

## 5. Xem Logs

### Request logs

1. Sidebar → **Logs**
2. Mỗi row là 1 request: request_id, timestamp, user, model, tokens, spend, latency, status (success/failure)
3. Click vào row → mở detail:
   - **Request body**: prompt/messages gửi lên
   - **Response body**: response từ model
   - **Metadata**: team, key, IP, tags, routing decision
   - **Cost breakdown**: input/output cost chi tiết
   - **Error** (nếu failure): traceback từ provider

### Filter hữu ích

- **User**: `duhd@vnpay.vn` — chỉ request của 1 user
- **Model**: `moonshot/kimi-k2.6` — chỉ request 1 model
- **Status**: `failure` — chỉ request lỗi (debug)
- **Date range**: 1h / 24h / 7d

### Log retention

- Request/response body lưu **7 ngày** (tự xóa 03:00 UTC = 10:00 ICT hàng ngày).
- Timestamp hiển thị trong UI Logs / Usage = giờ Hà Nội (ICT, UTC+7) từ 2026-04-23. Row cũ hơn lưu UTC trong DB → nếu query trực tiếp psql có thể lệch 7h, nhưng UI tự convert.
- Spend log (tokens + cost, không có body) lưu vô hạn — phục vụ billing.
- Full trace logs trong Jaeger (`sdlc-go-prod`) — liên hệ DevOps để xem.

---

## 6. Cấu hình Dev Tools

Mẫu chung: mọi tool cần **3 thông số**:
- **Base URL**: `https://api-llm.x.vnshop.cloud` (hoặc `/v1`, `/anthropic` tùy endpoint)
- **API Key**: virtual key bạn vừa tạo (`sk-...`)
- **Model**: tên model từ bảng mục 2

### 6.1 Claude Code CLI (Anthropic official)

Docs: https://code.claude.com/docs/en/llm-gateway

**Env vars** (thêm vào `~/.zshrc` / `~/.bashrc` / Windows System env):

```bash
export ANTHROPIC_BASE_URL="https://api-llm.x.vnshop.cloud"
export ANTHROPIC_AUTH_TOKEN="sk-your-virtual-key-here"

# Model mặc định cho các role
export ANTHROPIC_DEFAULT_OPUS_MODEL="claude-opus-4-6"
export ANTHROPIC_DEFAULT_SONNET_MODEL="claude-sonnet-4-6"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-haiku-4-5"

# Tùy chọn: override model cho small/fast tasks (title, summary, etc.)
export ANTHROPIC_SMALL_FAST_MODEL="moonshot/kimi-k2.6"
```

**Hoặc** cấu hình trong `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api-llm.x.vnshop.cloud",
    "ANTHROPIC_AUTH_TOKEN": "sk-your-virtual-key-here",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5",
    "ANTHROPIC_SMALL_FAST_MODEL": "moonshot/kimi-k2.6"
  }
}
```

**Lưu ý:**
- Dùng `ANTHROPIC_AUTH_TOKEN` (→ `Authorization: Bearer`), **KHÔNG** dùng `ANTHROPIC_API_KEY` (→ `X-Api-Key`, dành cho Anthropic trực tiếp).
- Nếu đã có Claude Pro/Max subscription + `ANTHROPIC_API_KEY` cùng lúc → API key sẽ thắng (xem thứ tự ưu tiên auth). `unset ANTHROPIC_API_KEY` để fallback về gateway.
- Kiểm tra nhanh: `claude` → `/status` để xem đang auth qua nguồn nào.

**Sử dụng model Kimi hoặc MiniMax** (dùng non-Claude models qua Anthropic format):

```bash
# Trong session
claude --model moonshot/kimi-k2.6

# Hoặc gõ trong chat:
# /model moonshot/kimi-k2.6
```

### 6.2 Claude Code Extension (VSCode / Antigravity)

Extension **dùng chung config với CLI** — đọc từ `~/.claude/settings.json` và env vars của shell.

**Nếu mở VSCode/Antigravity từ GUI (không qua terminal)**, env vars shell có thể không được load. Cách xử lý:

**macOS** — tạo `~/Library/LaunchAgents/anthropic.env.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>anthropic.env</string>
  <key>ProgramArguments</key><array>
    <string>sh</string><string>-c</string>
    <string>launchctl setenv ANTHROPIC_BASE_URL https://api-llm.x.vnshop.cloud; launchctl setenv ANTHROPIC_AUTH_TOKEN sk-xxx</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
```

Load: `launchctl load ~/Library/LaunchAgents/anthropic.env.plist`

**Windows** — Settings → System → About → Advanced system settings → Environment Variables → New user variable cho mỗi `ANTHROPIC_*`. Restart VSCode/Antigravity.

**Linux** — thêm vào `~/.profile` (không chỉ `~/.bashrc`) hoặc `~/.config/environment.d/anthropic.conf`.

Cách chắc nhất: **dùng `~/.claude/settings.json`** như ví dụ mục 6.1 — extension đọc trực tiếp, không phụ thuộc shell env.

### 6.3 Cline (VSCode extension)

Cline hỗ trợ 2 cách kết nối LiteLLM gateway:

**Cách A — Provider: Anthropic + Custom Base URL** (khuyên dùng, nhận được reasoning/thinking):

1. Click icon Cline ở sidebar VSCode → ⚙️ Settings
2. **API Provider**: chọn `Anthropic`
3. **API Key**: dán virtual key (`sk-...`)
4. **Model**: chọn Claude variant (ví dụ `claude-sonnet-4-5-20250929`)
5. Bật checkbox **"Use custom base URL"**
6. Nhập: `https://api-llm.x.vnshop.cloud`

**Cách B — Provider: LiteLLM** (native integration):

1. **API Provider**: chọn `LiteLLM`
2. **Base URL**: `https://api-llm.x.vnshop.cloud`
3. **API Key**: virtual key
4. **Model ID**: gõ tên model từ bảng mục 2 (ví dụ `moonshot/kimi-k2.6`)

**Cách C — OpenAI Compatible** (cho model non-Claude như Kimi, MiniMax):

1. **API Provider**: `OpenAI Compatible`
2. **Base URL**: `https://api-llm.x.vnshop.cloud/v1`
3. **API Key**: virtual key
4. **Model ID**: `moonshot/kimi-k2.6` hoặc `vnpay/minimax`
5. **Context window**: 262144 (Kimi) / 131072 (MiniMax on-prem)
6. **Max Output Tokens**: 16384

### 6.4 Cursor

⚠️ **Hạn chế quan trọng**: Cursor **không còn hỗ trợ custom OpenAI Base URL** trong version 2024+ cho các feature chính (Tab, Composer, Agent). Cursor bắt buộc gateway của Cursor với subscription riêng.

**Giải pháp thực tế**:

- Chuyển sang **Cline** (cùng là VSCode extension, nhiều tính năng tương đương Cursor Agent) — xem mục 6.3.
- Hoặc dùng **Cursor với Cline extension cài đè** — Cline chạy trong Cursor bình thường, dùng gateway VNPay cho Cline's agent, Cursor subscription chỉ dùng cho Tab autocomplete.
- Nếu bắt buộc dùng Cursor feature gốc → phải mua Cursor Pro (không qua được gateway VNPay).

### 6.5 Xcode 26+ (macOS)

Yêu cầu: **Xcode 26 trở lên** (macOS Tahoe). Tham khảo chi tiết + troubleshooting: [docs/xcode-intelligence-setup.md](./docs/xcode-intelligence-setup.md).

**Quy trình:**

1. **Xcode > Settings** (`⌘,`) → sidebar trái chọn **Intelligence**
2. Mục **Providers** → click **Add a Provider** → chọn **Internet Hosted**
3. Điền form:

   | Trường | Giá trị |
   |---|---|
   | **URL** | `https://api-llm.x.vnshop.cloud` |
   | **API Key Header** | `Authorization` |
   | **API Key** | `Bearer sk-your-virtual-key` |
   | **Description** | `VNPay AI Gateway` |

4. Click **Add** — Xcode gọi ngay `GET /v1/models` để verify. Nếu OK → provider hiện trong list.
5. Chọn model làm default (`Editor > Coding Intelligence > <model>` hoặc phím tắt `⌘+0`).

**Chú ý quan trọng** (tránh lỗi "Provider is not valid"):
- **URL KHÔNG có `/v1`** — Xcode tự append `/v1/models`, `/v1/chat/completions`.
- **API Key field phải có tiền tố `Bearer `** (có khoảng trắng) — Xcode không tự thêm.
- Test trước bằng curl nếu verify fail:
  ```bash
  curl https://api-llm.x.vnshop.cloud/v1/models -H "Authorization: Bearer sk-..."
  ```

### 6.6 Android Studio

❌ **Android Studio không hỗ trợ custom LLM provider out-of-the-box** (chỉ Gemini của Google với AI Studio key).

**Workaround qua plugin JetBrains**:

1. **CodeGPT** plugin (https://plugins.jetbrains.com/plugin/21056-codegpt):
   - Plugins marketplace → tìm `CodeGPT` → Install → restart.
   - Settings → Tools → CodeGPT → **Providers** → chọn `OpenAI` (hoặc `Custom`)
   - **Base Host**: `https://api-llm.x.vnshop.cloud/v1`
   - **API Key**: virtual key
   - **Model**: `moonshot/kimi-k2.6` (gõ tay nếu không có trong dropdown)

2. **Continue plugin** (nếu có phiên bản JetBrains — check marketplace)
3. **Proxy AI** plugin (alternative cho CodeGPT)

### 6.7 Qwen Code CLI

Docs: https://github.com/QwenLM/qwen-code

**Install**:
```bash
npm install -g @qwen-code/qwen-code@latest
# hoặc: brew install qwen-code
```

**Config** — tạo `~/.qwen/settings.json`:

```json
{
  "modelProviders": {
    "openai": [
      {
        "id": "kimi-k2.6",
        "name": "Kimi K2.6 via VNPay",
        "baseUrl": "https://api-llm.x.vnshop.cloud/v1",
        "envKey": "VNPAY_LITELLM_KEY"
      }
    ]
  },
  "env": {
    "VNPAY_LITELLM_KEY": "sk-your-virtual-key"
  },
  "security": {
    "auth": { "selectedType": "openai" }
  },
  "model": {
    "name": "kimi-k2.6"
  }
}
```

Model `id` map sang `model` field gửi lên API — phải khớp tên trong bảng mục 2 (ví dụ `moonshot/kimi-k2.6`). Nếu Qwen Code tự thêm prefix, thử giá trị `kimi-k2.6` trần hoặc kiểm tra debug log.

Chạy: `qwen` → tự động dùng config.

### 6.8 Aider

Docs: https://aider.chat/docs/llms/openai-compat.html

```bash
# Env vars
export OPENAI_API_BASE="https://api-llm.x.vnshop.cloud/v1"
export OPENAI_API_KEY="sk-your-virtual-key"

# Chạy với model
aider --model openai/moonshot/kimi-k2.6

# Hoặc Claude qua Anthropic-compat path
export ANTHROPIC_API_BASE="https://api-llm.x.vnshop.cloud"
export ANTHROPIC_API_KEY="sk-your-virtual-key"
aider --model claude-sonnet-4-6
```

Cờ `--no-show-model-warnings` để tắt warning "model không quen thuộc".

### 6.9 OpenAI SDK / custom scripts (Python / Node / curl)

Bất kỳ code gọi OpenAI SDK đều trỏ được về gateway:

**Python**:
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api-llm.x.vnshop.cloud/v1",
    api_key="sk-your-virtual-key",
)

resp = client.chat.completions.create(
    model="moonshot/kimi-k2.6",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

**Node (openai v4)**:
```js
import OpenAI from "openai";
const client = new OpenAI({
  baseURL: "https://api-llm.x.vnshop.cloud/v1",
  apiKey: process.env.VNPAY_LITELLM_KEY,
});
```

**curl test nhanh**:
```bash
curl https://api-llm.x.vnshop.cloud/v1/chat/completions \
  -H "Authorization: Bearer sk-your-virtual-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "moonshot/kimi-k2.6",
    "messages": [{"role":"user","content":"Say hi in 5 words"}],
    "max_tokens": 30
  }'
```

### 6.10 Codex CLI (OpenAI official)

Docs: https://github.com/openai/codex — Codex CLI hỗ trợ custom provider qua `config.toml`, dùng OpenAI-compatible API.

**Install**:
```bash
npm install -g @openai/codex
# hoặc: brew install codex
```

**Config** — sửa `~/.codex/config.toml` (tạo mới nếu chưa có):

```toml
# Default model + provider
model = "moonshot/kimi-k2.6"
model_provider = "vnpay"

# Tăng context reasoning (optional)
model_reasoning_effort = "medium"

[model_providers.vnpay]
name = "VNPay LiteLLM Gateway"
base_url = "https://api-llm.x.vnshop.cloud/v1"
env_key = "VNPAY_LITELLM_KEY"
wire_api = "chat"            # hoặc "responses" nếu dùng Responses API
# request_max_retries = 4
# stream_idle_timeout_ms = 300000

# (Optional) provider thứ 2 cho Claude qua Anthropic-compat path
[model_providers.vnpay-anthropic]
name = "VNPay Claude"
base_url = "https://api-llm.x.vnshop.cloud"
env_key = "VNPAY_LITELLM_KEY"
wire_api = "chat"
```

**Set API key** (env var khớp `env_key` trong config):

```bash
# Linux/macOS
export VNPAY_LITELLM_KEY="sk-your-virtual-key"

# Windows PowerShell
$env:VNPAY_LITELLM_KEY = "sk-your-virtual-key"
```

**Chạy**:

```bash
# Dùng model/provider mặc định (Kimi K2.6)
codex

# Override model cho 1 session
codex --model claude-sonnet-4-6 --config model_provider=vnpay-anthropic

# Non-interactive mode
codex exec "Refactor function foo in file bar.py"
```

**Sử dụng trong IDE** (Codex extension VSCode / JetBrains):

Extension đọc `~/.codex/config.toml` + env `VNPAY_LITELLM_KEY` giống CLI. Nếu mở IDE từ GUI (không qua terminal) → set env var ở OS level (xem hướng dẫn mục 6.2) hoặc giữ key trong config file với profile mặc định.

**Lưu ý:**
- `wire_api = "chat"` → gọi `/v1/chat/completions` (OpenAI format, hoạt động với mọi model gateway hỗ trợ).
- `wire_api = "responses"` → gọi `/v1/responses` (Responses API mới của OpenAI) — chỉ dùng khi model thực sự hỗ trợ, không khuyên cho Kimi/MiniMax/Claude qua LiteLLM.
- Model name phải khớp exact với bảng mục 2 — `moonshot/kimi-k2.6`, `claude-sonnet-4-6`, `MiniMax-M2.7`, etc.
- Kiểm tra nhanh: `codex --model moonshot/kimi-k2.6 exec "say hi"` — nếu 401 thì check `echo $VNPAY_LITELLM_KEY`.

### 6.11 Anthropic SDK

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="https://api-llm.x.vnshop.cloud",
    auth_token="sk-your-virtual-key",  # NOTE: auth_token, NOT api_key
)

msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
print(msg.content[0].text)
```

---

## 7. Fallback Chain

Gateway tự động chuyển request sang model khác khi model gốc fail (429 quota, 5xx, timeout, context overflow). User không phải retry thủ công — request vẫn hoàn tất, chỉ là **response có thể đến từ model khác model yêu cầu**.

### Primary fallback (model fail → model dự phòng)

Snapshot `2026-04-23`:

```
claude-opus          → moonshot/kimi-k2.6
claude-opus-4-5      → moonshot/kimi-k2.6
claude-opus-4-6      → moonshot/kimi-k2.6
claude-sonnet        → MiniMax-M2.7
claude-haiku-4-5     → vnpay/minimax
moonshot/kimi-k2.6   → moonshot/kimi-k2.5
moonshot/kimi-k2.5   → MiniMax-M2.7
MiniMax-M2.7         → vnpay/minimax
vnpay-medium         → vnpay/minimax
vnpay-simple         → vnpay/minimax
vnpay/minimax        → vnpay/v_glm46
```

**Topology**: mọi chain đều converge về on-prem (`vnpay/minimax` → `vnpay/v_glm46`, $0, zero egress, không bị cap budget) → request không bao giờ fail hoàn toàn nếu on-prem còn sống.

- **Claude Opus** (4-5 / 4-6 / alias) → **Kimi K2.6** (cùng tier coding/reasoning, intelligence index tương đương, rẻ hơn ~15x).
- **Claude Sonnet** → **MiniMax-M2.7** (cloud cheap long-context 1M).
- **Claude Haiku** → **vnpay/minimax** on-prem (tương đương tier small-fast-model).
- **Kimi K2.6** → **K2.5** (cùng provider, từ 2026-04-22 đã tách project budget riêng nên 2 key không chia sẻ cap).
- **Kimi K2.5** → **MiniMax-M2.7** (cloud cheap).
- **MiniMax-M2.7 / vnpay-medium / vnpay-simple** → **vnpay/minimax** (on-prem terminate).
- **vnpay/minimax** → **vnpay/v_glm46** (on-prem final hop, khác model weights để giảm correlated failure).

### Context window overflow

Khi prompt vượt context của model → escalate lên Claude Sonnet (200K):

```
vnpay-simple   (131K MiniMax on-prem)   → claude-sonnet (200K)
vnpay-medium   (262K Kimi K2.5)          → claude-sonnet (200K)
```

Các model khác (Kimi K2.6 256K, MiniMax-M2.7 1M, Claude 200K) đủ context cho mọi prompt thực tế nên không cần rule.

### Retry + cooldown

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `num_retries` | 2 | Retry 2 lần trên cùng deployment trước khi fallback |
| `allowed_fails` | 2 | 2 fail liên tiếp → deployment bị đánh dấu cooldown |
| `cooldown_time` | 60s | Deployment bị skip trong 60s sau cooldown |
| `timeout` (router) | 300s | Per-attempt deployment timeout |
| `request_timeout` (library) | 600s | Tổng budget cả fallback chain |
| `routing_strategy` | `simple-shuffle` | Random pick 1 trong N key cùng model (Kimi 3-key load balance) |

### Cách biết request đã bị fallback

Trong **Logs** → click detail request → xem:
- `model` field = model thực gateway call (không phải model client yêu cầu).
- `metadata.routing_reason` (nếu có) = lý do routing hook chọn model: `sensitive` / `simple` / `medium` / `complex_passthrough`.
- `model_id` + `api_base` = deployment cụ thể trong pool (hữu ích khi 1 model có nhiều key, ví dụ Kimi 3 project).

Ví dụ: gọi `claude-opus` → log hiện `model: moonshot/kimi-k2.6` nghĩa là Claude Opus đã fail và request được phục vụ bởi Kimi K2.6 fallback.

### Lưu ý quan trọng

- **Auth error (401/403) KHÔNG fallback** — fail fast. Nếu virtual key thiếu quyền dùng model → trả lỗi ngay, không thử model khác (tránh masking config bug).
- **Fallback không cover mọi 400**: Chỉ fallback khi upstream raise `ContextWindowExceededError` chính xác; provider trả 400 generic (ví dụ invalid tool schema) → fail luôn.
- **Budget-based 429 ≠ rate limit**: Moonshot trả 429 "exceeded consumption budget" (project budget cạn theo ngày) — LiteLLM coi là rate limit, cooldown 60s rồi retry → vẫn fail (budget reset theo ngày). Đã fix production: tăng cap + tách project silo. Nếu gặp spike fallback 100% → báo DevOps check budget.
- **Muốn TẮT fallback cho 1 request** (ví dụ workflow coding bắt buộc Claude, không chấp nhận response Kimi): gửi header/body `"disable_fallbacks": true` hoặc liên hệ DevOps disable cho key/team.
- **`simple-shuffle` không sticky**: 2 request liên tiếp có thể hit 2 Kimi key khác nhau → Moonshot prompt caching không tận dụng được (mỗi project cache riêng). Chấp nhận tradeoff để load balance đều.

---

## 8. Troubleshooting

### 401 Unauthorized

- Virtual key sai/hết hạn → regenerate trong UI.
- Với Claude Code: đang dùng `ANTHROPIC_API_KEY` thay vì `ANTHROPIC_AUTH_TOKEN` → `unset ANTHROPIC_API_KEY` rồi thử lại.
- Key bị revoke → admin check `/key/info?key=...`.

### 403 Forbidden — "model not in your allowed_models list"

Virtual key của bạn không có quyền dùng model đang request:
- UI → Virtual Keys → edit key → thêm model vào **Models** list.
- Hoặc đổi sang model khác trong allowed list.

### 400 — "thinking is enabled but reasoning_content is missing"

Model Kimi K2.6 thinking mode khó tính với conversation history thiếu `reasoning_content`. Đã có fix ở gateway (placeholder injection). Nếu vẫn gặp: thử clear chat history và start session mới.

### Request timeout / 504

- Gateway timeout = **600s** (library-level + WAF/CDN đồng bộ). Router per-attempt timeout 300s, cover được cả fallback chain trong 600s budget.
- Nếu dùng Claude Code/Cline và request > 10 min → check Jaeger trace qua DevOps.
- WAF VNPay phía trước có thể timeout 60s **TTFB** (time-to-first-byte) — nếu model chậm response token đầu → bị cắt. Chọn model khác / tách prompt nhỏ hơn / bật streaming (`stream: true`) để flush header sớm.

### UI hiển thị "0 results" / "No data" trên mọi tab

Triệu chứng: đăng nhập thấy dashboard bình thường nhưng Virtual Keys / Teams / Logs / Usage đều rỗng, không có error rõ ràng. Không phải mất data.

**Nguyên nhân**: session cookie hết hạn (TTL = 8h) nhưng cookie vẫn còn trong browser từ lần login cũ (trước fix 2026-04-23) → mọi XHR trả 401 im lặng → UI render empty state thay vì redirect SSO.

**Fix**:
1. DevTools → Application → Cookies → `litellm.x.vnshop.cloud` → xóa cookie `token`
2. Reload trang → tự redirect SSO → session mới
3. Hoặc đơn giản: mở cửa sổ Incognito

Từ 2026-04-23 trở đi, cookie tự xóa đúng 8h, không gặp tình trạng này nữa.

### "Missing `reasoning_content`" cho tool_use messages

(đã fix ở gateway từ 2026-04-22). Nếu vẫn gặp, báo DevOps — có thể model mới chưa được flag `supports_reasoning`.

### Cost không track / spend = 0

- Kiểm tra **Logs** tab xem status có phải `success` không — failure request không tính cost.
- Nếu success nhưng spend=0 cho model mới (Kimi K2.x, MiniMax) → báo DevOps để register pricing.

### Tool kêu "model not found"

- Tên model phải khớp exact — case-sensitive: `moonshot/kimi-k2.6` ≠ `Moonshot/Kimi-K2.6`.
- Một số tool thêm prefix provider tự động (`openai/...`) — thử bỏ/thêm prefix.

### Đổi model mặc định cho 1 repo

Tạo `.env` hoặc `.claude/settings.json` trong repo → override env vars cho project đó.

---

## 9. FAQ

**Q: Virtual key khác master key?**
- Master key: full permission, chỉ admin giữ, không nên phân phối.
- Virtual key: per-user/team, có budget limit, model scope, expiry — phân phối được.

**Q: Request qua gateway có gửi data ra ngoài không?**
- Model `vnpay-*` / `vnpay/v_glm46` / `vnpay/minimax` → 100% on-premise, zero egress.
- Model Claude / Kimi / MiniMax cloud → data gửi sang provider tương ứng (tuân thủ DPA). **Không gửi dữ liệu nhạy cảm** qua các model này.
- Routing hook có keyword detection tự động redirect PII → on-premise (xem README `Routing Hook`).

**Q: Làm sao biết gateway đã route / fallback sang model khác?**
Xem chi tiết cơ chế ở section **7. Fallback Chain**. Tóm tắt:
- **Logs** → detail request → `model` field = model thực sự phục vụ request.
- `metadata.routing_reason` = lý do routing hook chọn (`sensitive` / `simple` / `medium` / `complex_passthrough`).
- Nếu `model` ≠ model client yêu cầu → đã fallback do upstream fail (xem section 7 biết chain).

**Q: Quên gia hạn virtual key → key block đột ngột**
- UI cho phép set email alert khi spend > 80%/100% budget.
- Team admin có thể tăng budget bất kỳ lúc nào không cần tạo key mới.

**Q: Upload file/image support?**
- `claude-*` hỗ trợ vision (upload image qua message content).
- `moonshot/kimi-k2.x` hỗ trợ vision (multimodal).
- `vnpay-*` on-premise: text-only hoặc hỏi DevOps về multimodal support.

**Q: Gateway có log prompt/response thật không?**
- Có, lưu 7 ngày trong DB để debug. Sau 7 ngày tự xóa.
- Spend metadata (tokens + cost) lưu vô hạn.
- **Khuyến cáo**: không gửi password/secret qua prompt — dùng placeholder.

---

## Liên hệ

- Vấn đề gateway / model / quota: `duhd` Viber
- Bug UI / feature request: tạo ticket Jira project `litellm`
- Security incident: escalation sang `duhd` Viber

---

## Changelog

| Version | Ngày | Thay đổi |
|---|---|---|
| **1.0** | 2026-04-22 | Bản đầu: login flow, danh sách 15 model với benchmark Kimi K2.6, tạo virtual key (UI + CLI), xem usage + logs, cấu hình 10 tools (Claude Code CLI + VSCode/Antigravity, Cline, Cursor, Xcode 26, Android Studio, Qwen Code, Aider, OpenAI/Anthropic SDK), troubleshooting + FAQ |
| **1.1** | 2026-04-22 | Thêm section 6.10 Codex CLI (OpenAI official) — config `~/.codex/config.toml` với `model_providers.vnpay`, `wire_api = "chat"`, env `VNPAY_LITELLM_KEY` |
| **1.2** | 2026-04-23 | Troubleshooting: thêm "UI hiển thị 0 results trên mọi tab" (zombie session cookie, fix 2026-04-23 — browser cũ cần clear cookie 1 lần). Troubleshooting 504: làm rõ router timeout 300s + library 600s + WAF TTFB 60s, gợi ý streaming. FAQ: thêm mục giải thích fallback chain (claude-opus → Kimi → MiniMax → on-prem) và rule context window overflow |
| **1.4** | 2026-04-23 | Note timestamp UI hiển thị giờ Hà Nội (ICT, UTC+7) từ 2026-04-23 sau khi container set `TZ=Asia/Ho_Chi_Minh`. Row DB cũ hơn vẫn UTC. Cleanup job chạy 03:00 UTC = 10:00 ICT |
| **1.3** | 2026-04-23 | Thêm section **7. Fallback Chain** đầy đủ (snapshot DB): 11 rule primary + 2 context overflow, topology converge on-prem, bảng retry tunables (num_retries/allowed_fails/cooldown_time/timeout/routing_strategy), cách đọc `metadata.routing_reason` + `model_id` trong Logs, gotcha budget-based 429, disable fallback per-request, simple-shuffle không sticky. Dời FAQ fallback cũ thành link tới section 7. `request_timeout` library-level 600s (match WAF). Renumber: Troubleshooting 7→8, FAQ 8→9 |

**Đề xuất thay đổi**: tạo MR trên `git.vnpay.vn/duhd/litellm` sửa file `deploy/vnpay/USER_GUIDE.md`, hoặc báo `duhd` Viber.
