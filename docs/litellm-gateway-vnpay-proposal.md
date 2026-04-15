# LLM Gateway API — Nền tảng quản trị LLM tập trung cho VNPAY

> **Tài liệu nội bộ** | Ngày: 10/04/2026 | Trình bày: DuHD — AI Platform Team
> **Đối tượng**: Ban Tổng Giám đốc, Chủ tịch HĐQT, Ban Điều hành CN

---

## 1. Tóm tắt điều hành

VNPAY đang dự chi **~8.18 tỷ VND/năm** cho 149 subscription AI cá nhân (Claude Max, ChatGPT, Gemini, Adobe CC, Figma, và 20+ công cụ khác) trải rộng trên toàn bộ đơn vị. Chi phí này **phân tán, không kiểm soát được**, không có audit trail, và tiềm ẩn rủi ro rò rỉ dữ liệu doanh nghiệp.

**Giải pháp**: Triển khai **LLM Gateway API** — một cổng truy cập AI tập trung, chạy trên hạ tầng VNPayCloud nội bộ, kết nối tất cả nhà cung cấp AI (Anthropic, Kimi, MiniMax, VNPAY GenAI, và mở rộng thêm OpenAI, Google, DeepSeek...) qua một đầu mối duy nhất.

**Kết quả kỳ vọng**:
- Giảm **52-60% tổng chi phí AI** (~4.3–4.9 tỷ/năm) nhờ chuyển sang mô hình pay-per-use + intelligent routing; riêng phần LLM text (Anthropic/OpenAI/Google ~6.35 tỷ) tiết kiệm **68-77%**
- **Kiểm soát hoàn toàn** ai dùng gì, bao nhiêu, cho mục đích gì
- **Bảo vệ dữ liệu** — lọc thông tin nhạy cảm trước khi gửi ra ngoài
- **Nền tảng AI cho 20+ hệ thống nội bộ** (SOCCHAT, BAS, và các ứng dụng nghiệp vụ)

**Trạng thái**: Đã triển khai và vận hành production — 6 teams, 39 nhân sự, 4 AI providers kết nối.

---

## 2. Vấn đề hiện tại

### Chi phí phân tán, không kiểm soát

| Hiện trạng | Rủi ro |
|------------|--------|
| Mỗi nhân sự tự mua subscription AI riêng | Chi phí ~8.18 tỷ/năm (148 dòng, 571 TK, 40+ đơn vị), không tối ưu — nhiều TK dùng không hết quota |
| Không có báo cáo sử dụng tập trung | Không biết AI đang tạo giá trị bao nhiêu, ở đâu, cho ai |
| API keys nằm rải rác trên máy cá nhân | Rủi ro rò rỉ credentials, không revoke được khi nhân sự nghỉ việc |
| Mỗi hệ thống tự kết nối riêng tới provider | Không có guardrails chung, không kiểm soát dữ liệu gửi ra ngoài |

### Rủi ro dữ liệu

- Nhân sự có thể vô tình gửi **dữ liệu giao dịch, thông tin khách hàng, source code nhạy cảm** tới AI provider bên ngoài
- Không có lớp lọc nào giữa người dùng và AI provider — hoàn toàn phụ thuộc vào ý thức cá nhân
- Không có audit trail — nếu xảy ra sự cố rò rỉ, không truy vết được

---

## 3. Giải pháp: LLM Gateway API tập trung

### Mô hình hoạt động

```
        Người dùng & Hệ thống VNPAY
        ============================
   ~571 TK / ~800 người  SOCCHAT     BAS           20+ Hệ thống
   (Claude Code,        (Chatbot    (Tạo URD,     nghiệp vụ
    VS Code, Xcode)      nội bộ)    tài liệu)     (TAS, ...)  
        |               |              |               |
        +-------+-------+------+-------+-------+-------+
                |              |               |
                v              v               v
        +--------------------------------------------------+
        |              LLM Gateway API (LiteLLM)                |
        |                                                  |
        |  Quản lý truy cập    Guardrails bảo mật         |
        |  Theo dõi chi phí    Lọc dữ liệu nhạy cảm      |
        |  Giới hạn ngân sách  Chặn prompt injection       |
        |  Báo cáo sử dụng    Định tuyến thông minh       |
        |                                                  |
        |        Chạy trên VNPayCloud nội bộ               |
        +--------------------------------------------------+
                |              |               |
                v              v               v
          VNPAY GenAI     Anthropic        Kimi / MiniMax
          (On-premise)    (Claude)         + mở rộng thêm
          Dữ liệu nhạy   Task phức tạp    OpenAI, Google,
          cảm, zero egress                  DeepSeek...
```

### Nguyên tắc cốt lõi

- **Một cổng duy nhất**: Mọi truy cập AI đi qua gateway — không ai kết nối trực tiếp tới provider
- **Pay-per-use**: Chỉ trả tiền cho lượng sử dụng thực tế, không mua subscription cố định
- **Dữ liệu nhạy cảm không rời VNPAY**: Tự động route qua VNPAY GenAI on-premise
- **Kiểm soát tập trung**: Quản lý key, ngân sách, quyền truy cập model từ một dashboard

---

## 4. Ứng dụng kết nối qua LLM Gateway API

### 4.1 Công cụ phát triển phần mềm (~571 TK đăng ký, ~800 người dùng thực tế)

| Công cụ | Mô tả | Lợi ích |
|---------|--------|---------|
| **Claude Code** (Terminal, VS Code, Xcode) | AI coding assistant đọc/sửa code, chạy tests, tạo PR, debug | Tiết kiệm 3-5 giờ/dev/tuần cho coding tasks |
| **AI Code Review** | Tự động review merge request, phát hiện bugs, đề xuất cải tiến | Tăng chất lượng code, giảm thời gian review |

### 4.2 Hệ thống nghiệp vụ nội bộ (20+ hệ thống)

| Hệ thống | Chức năng | LLM Gateway API hỗ trợ |
|-----------|-----------|-------------------|
| **SOCCHAT** | Chatbot nội bộ phục vụ nhân viên VNPAY | Kết nối nhiều model, tự động lọc PII, kiểm soát chi phí per-session |
| **BAS** (Business Analysis AI) | Tạo tài liệu nghiệp vụ (URD, SRS) trong luồng SDLC | Route tới model phù hợp từng loại tài liệu, audit trail nội dung |
| **Các hệ thống khác** | QA Automation, Log Analysis, v.v. | Chuẩn API thống nhất — kết nối 1 lần, dùng được mọi model |

### 4.3 Lợi thế của mô hình gateway cho hệ thống nội bộ

- **Kết nối 1 lần**: Hệ thống chỉ cần tích hợp 1 API endpoint, không phải viết code riêng cho từng provider
- **Đổi model không đổi code**: Chuyển từ GPT-4o sang Claude hay VNPAY GenAI — chỉ thay đổi config tại gateway
- **Failover tự động**: Model A gặp sự cố → gateway tự chuyển sang Model B, hệ thống không bị gián đoạn
- **Guardrails chung**: Mọi hệ thống đều được bảo vệ bởi cùng một lớp lọc dữ liệu

---

## 5. Bảo mật & Kiểm soát dữ liệu

### 5.1 Guardrails — Lớp bảo vệ dữ liệu doanh nghiệp

Mọi request gửi tới AI đều đi qua lớp lọc bảo mật **tại gateway trên VNPayCloud**, trước khi dữ liệu rời khỏi hạ tầng VNPAY:

| Lớp bảo vệ | Chức năng | Ví dụ thực tế |
|-------------|-----------|---------------|
| **Lọc thông tin cá nhân (PII)** | Tự động che CCCD, SĐT, STK, email trước khi gửi ra ngoài | `"KH Nguyễn Văn A, SĐT 0901234567"` → `"KH [REDACTED], SĐT [REDACTED]"` |
| **Chặn prompt injection** | Phát hiện và chặn các cuộc tấn công thao túng AI | Ngăn kẻ xấu lợi dụng AI để trích xuất dữ liệu nội bộ |
| **Ngăn rò rỉ dữ liệu** | Chặn gửi API keys, credentials, source code nhạy cảm | Tự động detect và chặn nếu prompt chứa connection strings, private keys |
| **Lọc nội dung độc hại** | Chặn output không phù hợp quy chuẩn doanh nghiệp | Đảm bảo AI response phù hợp trong môi trường công sở |
| **Policy riêng VNPAY** | Tùy chỉnh rules theo chính sách nội bộ | VD: dữ liệu tài chính chưa public → bắt buộc route on-premise |

### 5.2 Bảo vệ dữ liệu nhạy cảm — Định tuyến thông minh

```
   Request chứa dữ liệu nhạy cảm          Request thông thường
   (giao dịch, KH, tài chính)              (code, tóm tắt, dịch thuật)
              |                                       |
              v                                       v
       VNPAY GenAI (On-premise)              Cloud AI (Claude, GPT-4o)
       Dữ liệu KHÔNG rời datacenter         Đã qua Guardrails lọc PII
       100% kiểm soát nội bộ                 Model mạnh cho task phức tạp
```

### 5.3 Kiểm soát truy cập & Audit

- **Virtual Key**: Mỗi nhân sự/hệ thống nhận key riêng — thu hồi ngay khi nghỉ việc hoặc thay đổi quyền
- **Audit log đầy đủ**: Ghi nhận mọi request — ai, lúc nào, model nào, bao nhiêu tokens, nội dung gì
- **Admin Dashboard**: Quản trị tập trung qua web UI, truy cập bảo mật qua SSO + xác thực đa yếu tố
- **Network security**: WAF/CDN bảo vệ, IP whitelist, mã hóa TLS toàn tuyến

### 5.4 An toàn chuỗi cung ứng phần mềm

> **Bài học thực tế**: 24/03/2026, hacker đã upload phiên bản phần mềm LiteLLM độc hại lên kho công cộng, thu thập API keys và credentials. Deployment VNPAY **KHÔNG bị ảnh hưởng** nhờ quy trình kiểm soát nghiêm ngặt.

Các biện pháp đang áp dụng:
- Pin phiên bản phần mềm theo mã hash cụ thể — không dùng phiên bản "latest" tự động
- Kiểm tra an toàn (IOC scan) trước mỗi lần nâng cấp
- Provider API keys cách ly hoàn toàn — nếu gateway bị tấn công, key gốc không bị lộ
- Giới hạn network — gateway chỉ gọi được tới các AI provider đã đăng ký

---

## 6. Phân tích chi phí

### 6.1 Phương pháp luận so sánh

So sánh hai mô hình chi phí dựa trên **dữ liệu thực tế** từ LLM Gateway API (LiteLLM) trong giai đoạn pilot, tập trung vào nhà cung cấp **Anthropic Claude** — provider chính trong hệ sinh thái AI VNPAY.

```
PHƯƠNG PHÁP LUẬN — 4 BƯỚC

  Bước 1            Bước 2                  Bước 3                    Bước 4
  Đo lường          Quy đổi tháng &         Kịch bản so sánh          Chiếu quy mô
  thực tế 8 ngày    Correction Factor       (không routing vs         571 TK / ~800 người
  ──────────        ───────────────         có routing)               ──────────────────
  Query DB          ① ×3.75 (8 ngày         A: API thuần              Extrapolate
  → token/user         → 30 ngày)           B: API + on-premise       × nhóm người
  → spend/user      ② ÷ 0.30 (30%           routing                  dùng pilot
  → active days        adoption             → So sánh với             → So sánh
                       → full adoption)     subscription              năm/năm
                    Tổng hệ số: ×12.5
```

> **Lưu ý phương pháp**: Pilot hiện tại chỉ đo được **~30% tác vụ thực tế** của người dùng đã onboard (họ vẫn đang dùng song song subscription cũ cho 70% tác vụ còn lại). Mọi con số dưới đây đều được điều chỉnh theo correction factor này để phản ánh chi phí tại full adoption.

### 6.2 Dữ liệu gốc — Pilot VNPAY (07/04 – 14/04/2026)

> **Nguồn**: LiteLLM PostgreSQL — `LiteLLM_SpendLogs` JOIN `LiteLLM_VerificationToken`
> **Phạm vi**: 42 nhân sự đã onboard, loại trừ system keys (goclaw-*) và ops accounts
> **Kỳ đo**: 8 ngày gần nhất có dữ liệu đầy đủ (07/04 – 14/04/2026), quy đổi sang tháng (×30/8 = ×3.75)

| Chỉ số | 8 ngày thực tế (raw) | Quy đổi 1 tháng (×3.75) |
|--------|--------------------|-----------------------|
| Người dùng có phát sinh chi phí | 26 / 42 người | 26 người |
| Tổng requests Anthropic | 1,785 | ~6,694 |
| Prompt tokens | 81,174,412 | ~304,403,295 |
| Completion tokens | 646,726 | ~2,425,223 |
| **Chi phí API ghi nhận** | **$77.15** | **~$289/tháng** |

### 6.3 Điều chỉnh Adoption Rate — Từ 30% → 100%

Nhân sự đang dùng LiteLLM cho ~30% tác vụ, 70% còn lại vẫn qua subscription cũ.

```
  Chi phí ghi nhận (8 ngày, 30% tác vụ)   $77.15
  × Quy đổi sang tháng                    × 3.75   (= 30 ÷ 8)
  = Chi phí 1 tháng tại 30% adoption      $289/tháng

  ÷ Adoption rate hiện tại                ÷ 0.30
  ──────────────────────────────────────────────────────────
  Chi phí ước tính (100% tác vụ, 1 tháng) ~$964/tháng  (26 pilot users)
  Hệ số điều chỉnh tổng:                  ×12.5  (= 3.75 ÷ 0.30)
```

### 6.4 Phân phối sử dụng — Power Law

Dữ liệu raw 8 ngày (chưa điều chỉnh) cho thấy phân phối Power Law điển hình:

```
Chi phí API ghi nhận theo người dùng (8 ngày, 30% tác vụ):

  quangnh2  ████████████████████████████████████  $37.06  (48%)
  linhdv    █████████████  $13.29  (17%)
  thanhdt   ████████████  $12.23  (16%)
  dinhpv    ████  $4.08  (5%)
  anhnt3    ███  $3.09  (4%)
  ─────────────────────────────────────────────────────────────
  Top 5 người = $69.75 (90% tổng chi phí)
  21 người còn lại = $7.40 (10% — TB $0.35/người/8 ngày)
```

**Sau điều chỉnh ×3.3 (full adoption)**:

| Nhóm | Pilot (người) | Chi phí API raw/tháng | Chi phí API full/tháng | Subscription Max 5/tháng |
|------|--------------|----------------------|----------------------|--------------------------|
| **Heavy** (top 5) | 5 | ~$35–$140 | ~$115–$460 | $100 |
| **Medium** | 5 | ~$8–$15 | ~$27–$50 | $100 |
| **Light** | 16 | ~$1–$3 | ~$3–$10 | $100 |
| **Occasional** (on-premise) | 16 | $0 | $0 | $100 |

**Nhận xét quan trọng**: Với Claude Max 5 ($100/người), API pay-per-use **luôn rẻ hơn subscription** — kể cả với heavy users ở mức full adoption. Intelligent routing tối ưu thêm bằng cách đẩy tác vụ đơn giản xuống Kimi/MiniMax, giảm chi phí cloud thêm 80-85%.

### 6.5 Hiện trạng đăng ký AI tại VNPAY (2026)

> **Nguồn**: "Đăng ký nhu cầu sử dụng tài khoản AI 2026 — tổng hợp" (nội bộ, **148 dòng**, 40+ đơn vị, **571 tài khoản**)

| Nhóm Provider | Loại subscription chính | Số TK | Chi phí/năm (VND) | Ghi chú |
|---------------|------------------------|-------|-------------------|---------|
| **Anthropic Claude** | Max $200, Max $100, Pro, Team, API | **263 TK** | **~3,000,000,000** | 46% tổng TK, ~45% ngân sách |
| **Google / Gemini** | Gemini Pro/Ultra/API, Google AI Ultra, NotebookLM | **145 TK** | **~2,440,000,000** | bao gồm cả API dùng chung ($2K/tháng) |
| **OpenAI / ChatGPT** | ChatGPT Plus/Business, OpenAI API | **76 TK** | **~1,050,000,000** | bao gồm OpenAI API ($2K/tháng) |
| **Creative & Productivity** | Adobe CC, Freepik, Figma, Canva, ElevenLabs, Capcut... | **80 TK** | **~970,000,000** | không route qua Gateway |
| **Coding & Dev tools** | GitHub Copilot Pro+, Codex Business, Replit, Manus... | **7 TK** | **~200,000,000** | một phần replace bằng Claude Code |
| **TỔNG** | **148 dòng đăng ký, 571 TK** | **571** | **~8,180,000,000** | nguồn: file tổng hợp nội bộ 2026 ¹ |

> ¹ **Ghi chú**: 7 dòng #VALUE (pay-per-usage API) không tính được chi phí cố định — tổng từ 141 dòng có số là ~6.66 tỷ, phần còn lại (~1.52 tỷ) ước tính từ các dòng API và Google Workspace. Tỷ giá: 1 USD = 26,335.5 VND.

**Chi tiết Claude — phân bổ theo loại tài khoản (từ file đăng ký 2026):**

| Loại | Số TK | Chi phí/năm (VND) | Đặc điểm |
|------|-------|-------------------|----|
| Claude Max $200 | 22 TK | ~1,369,000,000 | Heavy users — thường 5-10 người dùng chung 1 TK |
| Claude Max $100 | 16 TK | ~448,000,000 | Power users cá nhân + nhóm nhỏ |
| Claude Pro $20 | 191 TK | ~689,000,000 | Người dùng phổ thông, cá nhân |
| Claude Team (Premium/Standard) | 31 TK | ~471,000,000 | Team management + agentic workflows |
| Claude API | 3 TK | ~16,000,000+ | Tích hợp hệ thống (BAS, TCV...) — phần usage chưa tính |
| **Tổng Anthropic** | **263 TK** | **~2,993,000,000** | **~$113,600 USD/năm** |

> **Nhận xét**: Claude Max $200 (22 TK) chiếm **~46% chi phí Anthropic** — đây là heavy users dùng chung, thường 5-10 người/TK. Nhóm này tiết kiệm nhiều nhất khi chuyển sang API pay-per-use qua Gateway.

### 6.6 Bảng giá Anthropic — Subscription vs API

#### Anthropic Claude — Subscription

> **Nguồn**: [anthropic.com/news/max-plan](https://www.anthropic.com/news/max-plan)

| Gói | Giá/người/tháng | Usage limit (chính thức) | Ước tính messages/5h ¹ |
|-----|-----------------|--------------------------|------------------------|
| Claude Pro | $20 | Baseline | ~40–45 messages |
| Claude for Teams | $25 | Tương đương Pro + admin | ~40–45 messages |
| **Claude Max** (5×) | **$100** | **5× more usage than Pro** | **~225 messages** |
| **Claude Max** (20×) | **$200** | **20× more usage than Pro** | **~900 messages** |

> ¹ Con số messages/5h là **ước tính từ independent testers**, không phải số liệu chính thức của Anthropic. Thực tế thay đổi theo độ dài prompt, file đính kèm, context history và model sử dụng (Opus tốn nhiều hơn Haiku).
>
> **Cơ chế hoạt động**: Usage limit áp dụng theo **rolling window 5 giờ** (reset liên tục, không phải reset ngày). Từ 28/08/2025, Anthropic bổ sung thêm **weekly quota** — giới hạn 2 tầng (5h + tuần). Anthropic không công bố con số token tuyệt đối.
>
> **Nguồn**: [anthropic.com/news/max-plan](https://www.anthropic.com/news/max-plan) · [support.claude.com — usage limits](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work)
>
> VNPAY hiện tại: tổng Anthropic **~3.35 tỷ VND/năm** (216+ TK, tất cả các gói)

#### Anthropic API — Pay-per-use (qua LLM Gateway API)

> **Nguồn**: [anthropic.com/api/pricing](https://www.anthropic.com/api/pricing)

| Model | Input ($/M token) | Output ($/M token) | Batch API Input | Batch API Output |
|-------|-------------------|--------------------|-----------------|----|
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.50 | $2.50 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | $1.50 | $7.50 |
| Claude Opus 4.6 | $5.00 | $25.00 | $2.50 | $12.50 |

> **Batch API** (xử lý bất đồng bộ): giảm 50% chi phí — phù hợp cho tác vụ không yêu cầu real-time (code review, phân tích tài liệu hàng loạt, report generation).

#### Kimi — API (qua LLM Gateway API, routing Claude Sonnet thay thế)

> **Nguồn**: [platform.moonshot.cn/docs/pricing/models](https://platform.moonshot.cn/docs/pricing/models)

| Model | Input ($/M token) | Output ($/M token) | Điểm mạnh |
|-------|-------------------|--------------------|-----------|
| Kimi K2.5 | $0.60 | $2.50 | Coding, reasoning — ngang Claude Sonnet 4.6 |

> Kimi K2.5 là open-source model tương đương Claude Sonnet cho nhiều tác vụ, với chi phí **thấp hơn 5× về input và 6× về output**.

#### MiniMax — API (qua LLM Gateway API, routing tác vụ đơn giản)

> **Nguồn**: [platform.minimax.io/docs/guides/pricing-paygo](https://platform.minimax.io/docs/guides/pricing-paygo)

| Model | Input ($/M token) | Output ($/M token) | Điểm mạnh |
|-------|-------------------|--------------------|-----------|
| MiniMax M2.7 (standard) | $0.30 | $1.20 | Tóm tắt, phân loại, format — cost-effective |
| MiniMax M2.7-highspeed | $0.60 | $2.40 | Latency thấp, real-time applications |

> MiniMax M2.7 có chi phí input **thấp hơn 10× so với Claude Sonnet** — phù hợp cho tác vụ đơn giản không cần model mạnh.

### 6.7 Chiến lược Intelligent Routing — Mô hình VNPAY

LLM Gateway API tự động phân loại và route mỗi request tới provider tối ưu về **chất lượng × chi phí**:

| Loại tác vụ | Ví dụ | Route | Chi phí |
|-------------|-------|-------|---------|
| **Nhạy cảm / nội bộ** | Dữ liệu giao dịch, KH, tài chính | VNPAY GenAI (on-premise) | $0 (zero egress) |
| **Đơn giản** (format, dịch, tóm tắt) | Format code, dịch document, tóm tắt meeting | MiniMax M2.7 | ~$0.30/$1.20 per MTok |
| **Trung bình** (coding, analysis) | Debug code, viết unit test, phân tích yêu cầu | Kimi K2.5 | ~$0.60/$2.50 per MTok |
| **Phức tạp** (architecture, deep reasoning) | Thiết kế kiến trúc, audit bảo mật, phân tích chiến lược | Claude Sonnet/Opus | $3–$5/$15–$25 per MTok |

```
ROUTING DECISION FLOW

  Request vào LLM Gateway API
         |
         v
  ┌─────────────────────────────┐
  │ Có chứa dữ liệu nhạy cảm? │ → YES → VNPAY GenAI (on-premise, $0)
  └─────────────────────────────┘
         | NO
         v
  ┌─────────────────────────────┐
  │ Task complexity classifier  │
  │ (prompt length + keywords)  │
  └─────────────────────────────┘
         |
    ┌────┴────┐
    │         │
   LOW      HIGH
    │         │
    v         v
 MiniMax   Kimi K2.5    → nếu cần model mạnh nhất → Claude Sonnet/Opus
 ($0.30)   ($0.60)
```

**Kết quả routing tối ưu (ước tính phân bổ tác vụ)**:
- 30% tác vụ → VNPAY GenAI on-premise: **$0**
- 30% tác vụ → MiniMax M2.7: **~$0.30–$1.20/MTok**
- 25% tác vụ → Kimi K2.5: **~$0.60–$2.50/MTok**
- 15% tác vụ → Claude Sonnet/Opus: **$3–$25/MTok**

### 6.8 Hai kịch bản tại full adoption

```
Kịch bản A: API thuần — KHÔNG có routing tối ưu
(toàn bộ tác vụ dùng Claude cloud)

  26 pilot users × full adoption:          ~$964/tháng
  Subscription 26 users (Claude Max 5):  ~$2,600/tháng
  ───────────────────────────────────────────────────────
  Kết quả: API RẺ HƠN $1,636/tháng (63%)
  Nhưng: chưa tối ưu — vẫn dùng 100% Claude cloud


Kịch bản B: API + Intelligent Routing  ← Mô hình VNPAY thực tế
(Kimi/MiniMax/on-premise cho 85% tác vụ, Claude cloud chỉ 15%)

  Chi phí nếu 100% API cloud:            $964/tháng
  → Sau routing Kimi/MiniMax/on-premise: ~$193/tháng  (×0.20)
  Subscription 26 users (Claude Max 5):  $2,600/tháng
  ───────────────────────────────────────────────────────
  Tiết kiệm vs subscription:             $2,407/tháng (93%)
```

**Routing là cốt lõi của ROI** — không phải tính năng tùy chọn. Xem chi tiết routing strategy tại mục 6.6.

### 6.9 Chiếu quy mô thực tế VNPAY — Kịch bản B (Routing đầy đủ: Kimi + MiniMax + On-premise)

**Dữ liệu gốc** (file đăng ký nội bộ 2026): **571 tài khoản** / **148 dòng đăng ký** / **~800 người dùng thực tế**
(Do shared accounts: ví dụ 30 TK Gemini cho ~90 người tại KCN_DVNH, 5 TK Claude Max $200 cho ~25 người tại KCN_DVTT)

| Nhóm | Số lượng (thực tế) | Route | Chi phí/người/tháng | Tổng/tháng |
|------|-------------------|-------|--------------------|-----------:|
| Heavy (10%) | ~80 người | 15% Claude + 25% Kimi + 60% MiniMax/on-premise | ~$30 | ~$2,400 |
| Medium (20%) | ~160 người | 10% Claude + 30% Kimi + 60% MiniMax/on-premise | ~$8 | ~$1,280 |
| Light (40%) | ~320 người | 5% Claude + 15% Kimi + 80% MiniMax/on-premise | ~$1.5 | ~$480 |
| Occasional (30%) | ~240 người | 100% on-premise | $0 | $0 |
| **Tổng** | **~800 người** | | | **~$4,160/tháng** |

```
So sánh tại quy mô thực tế VNPAY (571 TK / ~800 người) — Routing đầy đủ:

  Subscription hiện tại (thực tế 2026, 148 dòng, 571 TK):   8.18 tỷ VND/năm  ≈ $321,500/năm
  Trong đó phần LLM text (Claude + ChatGPT + Gemini):           ~$249,900/năm
  API + Routing đầy đủ (kịch bản B, ~800 người):                ~$49,920/năm
                                                    ──────────────────────────────────
  Tiết kiệm hàng năm (phần LLM):                              ~$199,980/năm  ≈ ~5.1 tỷ VND
  Tiết kiệm hàng tháng:                                        ~$16,665/tháng ≈ ~425 triệu VND
  Tỷ lệ tiết kiệm (phần LLM):                                   80%
```

> **Ghi chú**: Phần Creative tools (Adobe CC, Figma, Canva, Freepik... ~1.83 tỷ VND) không thể thay thế bằng LLM Gateway API → **tổng tiết kiệm thực tế 52-60%** trên toàn bộ 8.18 tỷ.

### 6.10 Tổng chi phí toàn bộ AI (tất cả providers)

Áp dụng cùng mô hình cho ChatGPT Plus ($20/tháng), Gemini Advanced ($22/tháng) và các tool AI khác (routing về OpenAI/Gemini API tương ứng):

```
  Chi phí subscription thực tế (toàn bộ AI, 2026):     8.18 tỷ VND/năm
  Trong đó phần LLM text (Anthropic + OpenAI + Google): ~6.35 tỷ VND/năm
  Chi phí API Gateway — kịch bản B, routing đầy đủ:   ~1.5–2.0 tỷ VND/năm
                                                       ──────────────────────
  Tiết kiệm kỳ vọng (phần LLM):                       ~4.3–4.9 tỷ VND/năm  (68–77%)
  Phần Creative tools (Adobe, Figma...):               ~1.83 tỷ — giữ nguyên (không thay thế được)
  ──────────────────────────────────────────────────────────────────────────────────────
  Tổng chi phí AI sau Gateway:                         ~3.3–3.9 tỷ VND/năm
  Tiết kiệm tổng thể:                                  ~4.3–4.9 tỷ VND/năm  (52–60%)
```

> **Độ tin cậy**: Ước tính dựa trên 8 ngày dữ liệu thực tế với correction factor 30% adoption, sau đó tối ưu thêm với routing Kimi/MiniMax. Sai số ±20% tùy mức độ adoption thực tế và tỷ lệ routing. Sau 30 ngày full adoption, con số sẽ được hiệu chỉnh từ data thực.

### 6.11 Cơ cấu chi phí LLM Gateway API

| Khoản mục | Chi phí | Ghi chú |
|-----------|---------|---------|
| **Hạ tầng K8s (VNPayCloud)** | Dùng chung cluster hiện tại | Không phát sinh thêm |
| **Phần mềm LiteLLM** | Miễn phí (open-source) | 30K+ GitHub stars |
| **VNPAY GenAI on-premise (v_glm46)** | Hạ tầng sẵn có | Unlimited, $0 marginal cost, zero data egress |
| **MiniMax M2.7** | ~$0.30/$1.20 per MTok | Tác vụ đơn giản — low-cost tier |
| **Kimi K2.5** | ~$0.60/$2.50 per MTok | Tác vụ coding/analysis — mid-cost tier |
| **Anthropic Claude** | ~$3–$25 per MTok | Chỉ tác vụ phức tạp — high-value tier |
| **WAF/CDN + IP tĩnh** | Chi phí tối thiểu | Bảo mật tầng mạng |
| **Tổng API usage (~800 người, 571 TK)** | **~$4,160/tháng** | Kiểm soát qua budget limits per-team |

**Bốn nguồn tiết kiệm có thể đo lường được**:
1. **Loại bỏ subscription dư**: 70% nhân sự (light + occasional) trả $0–$2/tháng thay vì $20 cố định
2. **On-premise routing**: ~30% tác vụ nhạy cảm → v_glm46 ($0) — zero data egress
3. **Kimi/MiniMax routing**: ~55% tác vụ còn lại → chi phí thấp hơn 5-10× so với Claude
4. **Không mua dư quota**: Chấm dứt tình trạng quota subscription reset hàng tháng không dùng hết

---

## 7. Tăng năng suất nhân sự

### 7.1 Developer Productivity (~800 người dùng thực tế, 571 TK đăng ký)

| Chỉ số | Ước tính |
|--------|----------|
| Thời gian tiết kiệm | 3-5 giờ/dev/tuần (coding, debug, review) |
| Quy đổi | ~800 người x 4 giờ/tuần x 48 tuần = **~153,600 giờ/năm** |
| Giá trị (theo chi phí nhân sự) | Tương đương **~80 FTE** năng suất bổ sung |

### 7.2 Hệ thống nghiệp vụ

| Hệ thống | Tác động |
|-----------|----------|
| **SOCCHAT** | Giảm tải helpdesk nội bộ, trả lời 24/7 |
| **BAS** | Rút ngắn thời gian tạo tài liệu URD từ ngày xuống giờ |
| **AI Code Review** | Tự động review 100% merge request, phát hiện sớm lỗi |

### 7.3 Báo cáo AI Usage Analytics — Tự động hàng tuần

LLM Gateway API tích hợp **agent phân tích tự động**, mỗi tuần gửi báo cáo chi tiết tới ban quản lý:

**Nội dung báo cáo**:

| Mục | Chi tiết |
|-----|---------|
| **Executive Summary** | Tổng request, tokens, chi phí, số người dùng active, top model |
| **Chi phí theo team & cá nhân** | Breakdown chi tiết: ai dùng bao nhiêu, model nào, tốn bao nhiêu |
| **Chấm điểm hiệu quả sử dụng** | Mỗi nhân sự được đánh giá 4 chiều (1-10): Chất lượng prompt, Độ phức tạp task, Hiệu quả token, Mức độ adoption |
| **Mẫu prompt thực tế** | Trích dẫn 3-5 prompt mỗi người, đánh giá điểm mạnh và cần cải thiện |
| **Phân bổ theo thời gian & model** | Giờ nào dùng nhiều nhất, model nào phổ biến, error rate |
| **Xu hướng tuần-qua-tuần** | So sánh tăng/giảm request, tokens, chi phí, adoption |
| **Đề xuất cho quản lý** | Gợi ý tối ưu chi phí, cơ hội đào tạo, nhân sự cần hỗ trợ |

**Giá trị cho ban lãnh đạo**: Lần đầu tiên VNPAY có **data-driven visibility** về việc ~800 người (571 TK đăng ký, 148 dòng đề xuất, 40+ đơn vị) đang sử dụng AI như thế nào — không chỉ chi phí mà cả **chất lượng và hiệu quả** sử dụng.

---

## 8. Chiến lược AI toàn công ty

### 8.1 Từ phân tán đến nền tảng

```
Trước (Q1/2026)              Hiện tại (04/2026)            Mục tiêu (05/2026)
─────────────────────        ─────────────────────         ─────────────────────
571 TK / ~800 người          Gateway production            Nền tảng AI toàn công ty
dùng AI riêng lẻ, phân tán  6 teams, 39 nhân sự           tự phục vụ (self-service)
                             4 providers kết nối
- Không kiểm soát           - Quản lý key tập trung       - ~800 người + 20 hệ thống
- Không đo lường            - Theo dõi chi phí            - SOCCHAT, BAS kết nối
- Rủi ro dữ liệu           - Audit log đầy đủ            - Guardrails bảo vệ
- ~8.18 tỷ/năm phân tán    - Báo cáo sử dụng tuần       - SSO tích hợp AD VNPAY
```

### 8.2 Lợi thế cạnh tranh

- **Tốc độ triển khai AI**: Hệ thống mới kết nối AI trong vài giờ thay vì vài tuần (chuẩn API sẵn có)
- **Data sovereignty**: Dữ liệu nhạy cảm xử lý 100% on-premise — đáp ứng yêu cầu NHNN và compliance
- **Vendor independence**: Không phụ thuộc một provider — chuyển đổi Claude ↔ GPT ↔ GenAI không ảnh hưởng hệ thống
- **Đo lường ROI AI**: Là một trong số ít doanh nghiệp có data chi tiết về hiệu quả sử dụng AI

---

## 9. Lộ trình triển khai — Hoàn thiện trong 1 tháng

```
Tuần 1 (14-18/04)     Tuần 2 (21-25/04)     Tuần 3 (28/04-02/05)   Tuần 4 (05-09/05)
─────────────────     ─────────────────     ──────────────────     ─────────────────
  Nền tảng &            Mở rộng &             Hệ thống              Toàn công ty &
  Pilot                 Guardrails            nghiệp vụ             Go-Live
  ██████████            ██████████            ██████████             ██████████
```

| Tuần | Nội dung | Kết quả đạt được | Trạng thái |
|------|----------|-------------------|------------|
| **Tuần 1** — Nền tảng & Pilot | Gateway production, 6 teams, 39 nhân sự onboard, 4 providers kết nối, báo cáo analytics tuần đầu | Gateway hoạt động ổn định, 44 API keys đã cấp, data chi phí thực tế | **Hoàn tất** |
| **Tuần 2** — Mở rộng & Guardrails | Onboard thêm developer (cộng dồn ~150), bật Guardrails (PII, prompt injection), Grafana dashboard chi phí | ~150 dev active, Guardrails bảo vệ dữ liệu, dashboard chi phí real-time | **Đang triển khai** |
| **Tuần 3** — Hệ thống nghiệp vụ | Kết nối SOCCHAT, BAS qua gateway, onboard tiếp (cộng dồn ~300), backup & monitoring | 20+ hệ thống kết nối, ~300 dev active, production hardening hoàn tất | Kế hoạch |
| **Tuần 4** — Go-Live toàn công ty | Onboard toàn bộ ~800 người (571 TK), self-service portal, SSO tích hợp AD VNPAY, báo cáo tổng kết tháng đầu | **Toàn bộ ~800 người + 20 hệ thống** hoạt động qua LLM Gateway API | Kế hoạch |

**Sau Go-Live** (liên tục cải tiến):
- Mở rộng on-premise model (Ollama) cho dữ liệu nhạy cảm
- Device pairing cho mobile developers
- Tối ưu routing policy dựa trên data sử dụng thực tế
- Báo cáo AI Usage Analytics hàng tuần cho ban lãnh đạo

---

## 10. Đề xuất & Phê duyệt

### Đề xuất

1. **Phê duyệt chuyển đổi** từ mô hình subscription cá nhân sang LLM Gateway API tập trung
2. **Phê duyệt ngân sách API usage** (cloud providers) — thay thế chi phí subscription hiện tại
3. **Chỉ đạo các đơn vị** (SOCCHAT, BAS, các hệ thống AI) kết nối qua LLM Gateway API

### Cam kết

- **Tiết kiệm 52-60%** tổng chi phí AI (~4.3–4.9 tỷ VND/năm), riêng phần LLM text tiết kiệm 68-77% (nhờ pay-per-use + routing Kimi + MiniMax + On-premise)
- **Kiểm soát 100%** truy cập AI với audit trail đầy đủ
- **Bảo vệ dữ liệu** nhạy cảm qua Guardrails và on-premise routing
- **Báo cáo định kỳ** về chi phí, hiệu quả sử dụng, và ROI

### Rủi ro & Giảm thiểu

| Rủi ro | Xác suất | Giảm thiểu |
|--------|----------|------------|
| Gateway gặp sự cố | Thấp | HA 2 replicas, zero-downtime upgrade, auto-failover |
| Supply chain attack | Thấp | Pin version theo hash, IOC scan, secrets cách ly (đã chứng minh qua sự cố 24/03) |
| Provider tăng giá | Trung bình | Multi-provider — chuyển đổi linh hoạt, tăng tỷ trọng on-premise |
| Nhân sự không adopt | Trung bình | Onboard từng giai đoạn, hỗ trợ setup, báo cáo adoption tuần |

---

**Trạng thái hiện tại**: Gateway đang vận hành production — 6 teams (DVTT-KCN, UDDD-iOS, DVNH-KCN, GSVH-KCN, eFIN-KCN, ops-litellm), 44 API keys đã cấp (39 nhân sự + 5 system), 4 providers kết nối (Anthropic, Kimi, MiniMax, VNPAY GenAI GLM-4)
