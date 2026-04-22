# LiteLLM VNPay — User Guide

> **Version 1.0** — cập nhật `2026-04-22` · [Changelog](#changelog) · Nguồn chính thức: [github.com/duhd-vnpay/litellm/blob/main/deploy/vnpay/USER_GUIDE.md](https://github.com/duhd-vnpay/litellm/blob/main/deploy/vnpay/USER_GUIDE.md)

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

- Request/response body lưu **7 ngày** (tự xóa 03:00 UTC hàng ngày).
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

### 6.10 Anthropic SDK

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

## 7. Troubleshooting

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

- Gateway timeout = 600s (đủ cho 99% case).
- Nếu dùng Claude Code/Cline và request > 10 min → check Jaeger trace qua DevOps.
- WAF VNPay phía trước có thể timeout 60s nếu TTFB chậm → chọn model khác / tách request nhỏ hơn.

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

## 8. FAQ

**Q: Virtual key khác master key?**
- Master key: full permission, chỉ admin giữ, không nên phân phối.
- Virtual key: per-user/team, có budget limit, model scope, expiry — phân phối được.

**Q: Request qua gateway có gửi data ra ngoài không?**
- Model `vnpay-*` / `vnpay/v_glm46` / `vnpay/minimax` → 100% on-premise, zero egress.
- Model Claude / Kimi / MiniMax cloud → data gửi sang provider tương ứng (tuân thủ DPA). **Không gửi dữ liệu nhạy cảm** qua các model này.
- Routing hook có keyword detection tự động redirect PII → on-premise (xem README `Routing Hook`).

**Q: Làm sao biết routing hook đã route sang model khác?**
- Xem **Logs** → detail request → metadata có field `routing_reason` (nếu có, giá trị: `sensitive` / `simple` / `medium` / `complex_passthrough`).
- Field `model` hiển thị model thực gateway call, không phải model client yêu cầu.

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

**Đề xuất thay đổi**: tạo PR trên fork `duhd-vnpay/litellm` sửa file `deploy/vnpay/USER_GUIDE.md`, hoặc báo `duhd` Viber.
