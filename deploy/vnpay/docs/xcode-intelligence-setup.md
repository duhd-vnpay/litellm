# Hướng dẫn cấu hình Xcode Intelligence dùng LiteLLM Gateway VNPay

> **Version 1.1** — cập nhật `2026-04-22` · Bản rút gọn trong [USER_GUIDE.md §6.5](../USER_GUIDE.md#65-xcode-26-macos)

## Yêu cầu

- Xcode 26 trở lên (macOS Tahoe)
- API key của LiteLLM Gateway VNPay (liên hệ team AI Platform để được cấp)

---

## Cách cấu hình

### Bước 1: Mở Intelligence Settings

Vào **Xcode > Settings** (⌘,) → chọn **Intelligence** ở sidebar trái.

### Bước 2: Thêm Provider

Trong mục **Providers**, click **Add a Provider**.

### Bước 3: Điền thông tin provider

Chọn **Internet Hosted**, điền các trường sau:

| Trường | Giá trị |
|---|---|
| **URL** | `https://api-llm.x.vnshop.cloud` |
| **API Key Header** | `Authorization` |
| **API Key** | `Bearer <your-litellm-key>` |
| **Description** | `VNPay AI Gateway` |

Click **Add**.

> **Lưu ý:**
> - **URL không có `/v1`** — Xcode tự động gọi `{URL}/v1/models` và `{URL}/v1/chat/completions`
> - **API Key phải có tiền tố `Bearer `** (có khoảng trắng) — ví dụ: `Bearer sk-litellm-xxxx`

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

Mở **Coding Assistant** (⌘+0 hoặc **View > Coding Assistant**) và bắt đầu chat.

---

## Lưu ý về dữ liệu

| Model | Backend | Egress |
|---|---|---|
| `vnpay-simple`, `vnpay-medium` | Moonshot AI (Kimi K2.5) | Data ra ngoài VNPAY |
| `claude-sonnet`, `claude-opus` | Anthropic | Data ra ngoài VNPAY |
| `vnpay-sensitive` | On-premise VNPAY (GLM-4) | **Zero egress** — an toàn cho dữ liệu nội bộ |

---

## Troubleshooting

**"Provider is not valid — Models could not be fetched"**

Xcode gọi `GET /v1/models` ngay khi bấm **Add** — lỗi này do API key không hợp lệ hoặc sai format.

Kiểm tra key trước bằng Terminal:
```bash
curl https://api-llm.x.vnshop.cloud/v1/models \
  -H "Authorization: Bearer <your-key>"
```
Nếu trả về JSON danh sách model → key đúng, kiểm tra lại Xcode đã nhập đủ `Bearer ` chưa.

Điền đúng trong dialog Xcode:
- **API Key Header**: `Authorization`
- **API Key**: `Bearer sk-litellm-xxxx` ← phải có chữ `Bearer` và dấu cách

> Xcode không tự thêm `Bearer` — phải nhập đầy đủ vào field API Key.

**Xcode không hiện model nào sau khi add provider**
- Kiểm tra URL không có trailing slash và không có `/v1`
- Kiểm tra API key có đúng tiền tố `Bearer ` (có khoảng trắng)
- Kiểm tra kết nối bằng Terminal:
  ```bash
  curl https://api-llm.x.vnshop.cloud/v1/models \
    -H "Authorization: Bearer <your-key>"
  ```

**Lỗi 401 Unauthorized**
- API key sai hoặc hết hạn — liên hệ team AI Platform

**Lỗi 504 Gateway Timeout**
- Request quá lớn hoặc model đang bận — thử lại hoặc chọn model khác

**Response chậm (>30s)**
- Bình thường với context dài — Kimi K2.5 có TTFT ~5-6s cho prompt lớn

---

## Thông tin kỹ thuật

Xcode Intelligence giao tiếp với custom provider qua 2 endpoint chuẩn OpenAI Chat Completions API:

```
GET  {URL}/v1/models           — lấy danh sách model khả dụng
POST {URL}/v1/chat/completions — gửi request chat
```

LiteLLM Gateway VNPay tương thích hoàn toàn với OpenAI Chat Completions API format.

---

*Ref: [Apple Developer Documentation — Setting up coding intelligence](https://developer.apple.com/documentation/xcode/setting-up-coding-intelligence#Use-another-provider)*
