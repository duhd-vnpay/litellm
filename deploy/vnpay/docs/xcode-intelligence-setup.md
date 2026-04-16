# Hướng dẫn cấu hình Xcode Intelligence dùng LiteLLM Gateway VNPay

## Yêu cầu

- Xcode 26 trở lên (macOS Tahoe)
- API key của LiteLLM Gateway VNPay (liên hệ team AI Platform để được cấp)

---

## Cách cấu hình

### Bước 1: Mở Intelligence Settings

Vào **Xcode > Settings** (⌘,) → chọn **Intelligence** ở sidebar trái.

### Bước 2: Thêm Chat Provider

Trong mục **Chat**, click **Add a Chat Provider**.

### Bước 3: Điền thông tin provider

Chọn **Internet Hosted**, điền các trường sau:

| Trường | Giá trị |
|---|---|
| **URL** | `https://api-llm.x.vnshop.cloud` |
| **API Key Header** | `Authorization` |
| **API Key** | `Bearer <your-litellm-key>` |
| **Description** | `VNPay AI Gateway` |

> **Lưu ý quan trọng:**
> - **URL không có `/v1`** — Xcode tự động append `/v1/models` và `/v1/chat/completions`
> - **API Key phải có tiền tố `Bearer `** (có khoảng trắng) — ví dụ: `Bearer sk-litellm-xxxx`

Click **Add**.

### Bước 4: Chọn model

Sau khi add, Xcode gọi `GET /v1/models` để lấy danh sách model. Chọn model phù hợp:

| Model | Dùng cho |
|---|---|
| `vnpay-simple` | Tác vụ đơn giản: dịch, tóm tắt, format code |
| `vnpay-medium` | Coding, debug, code review, analysis |
| `claude-sonnet` | Kiến trúc, reasoning phức tạp, bảo mật |
| `claude-opus` | Tác vụ chiến lược, phân tích sâu |
| `vnpay-sensitive` | Dữ liệu nội bộ nhạy cảm (zero data egress) |

### Bước 5: Sử dụng

Mở **Coding Assistant** (⌘+0 hoặc View > Coding Assistant) và bắt đầu chat.

---

## Lưu ý về dữ liệu

- **`vnpay-simple`, `vnpay-medium`**: Request được forward đến Moonshot AI (Kimi K2.5) — không dùng cho dữ liệu nhạy cảm
- **`claude-sonnet`, `claude-opus`**: Request được forward đến Anthropic — không dùng cho dữ liệu nhạy cảm
- **`vnpay-sensitive`**: Chạy on-premise tại VNPAY, **zero data egress** — dùng được cho dữ liệu nội bộ

---

## Troubleshooting

**Xcode không hiện model nào sau khi add provider**
- Kiểm tra URL không có trailing slash và không có `/v1`
- Kiểm tra API key có tiền tố `Bearer ` (đúng chính tả, có khoảng trắng)
- Thử mở Terminal và test: `curl https://api-llm.x.vnshop.cloud/v1/models -H "Authorization: Bearer <your-key>"`

**Lỗi 401 Unauthorized**
- API key sai hoặc hết hạn — liên hệ team AI Platform

**Lỗi 504 Gateway Timeout**
- Request quá lớn hoặc model đang bận — thử lại hoặc dùng model khác

**Response chậm (>30s)**
- Bình thường với context dài hoặc câu hỏi phức tạp — kimi-k2.5 có TTFT ~5-6s cho prompt lớn

---

## Thông tin kỹ thuật

Xcode Intelligence giao tiếp với custom provider qua hai endpoint chuẩn OpenAI:

```
GET  {URL}/v1/models          — liệt kê danh sách model
POST {URL}/v1/chat/completions — gửi request chat
```

LiteLLM Gateway VNPay tương thích hoàn toàn với OpenAI Chat Completions API format.

Sources:
- [Apple Developer Documentation — Setting up coding intelligence](https://developer.apple.com/documentation/xcode/setting-up-coding-intelligence#Use-another-chat-provider)
