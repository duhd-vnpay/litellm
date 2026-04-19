"""
VNPay Intelligent Routing Hook
================================
Pre-call hook tự động phân loại request và route tới provider tối ưu:

  Tier 0 — Sensitive  → VNPAY GenAI on-premise (v_glm46)  — $0, zero egress
  Tier 1 — Simple     → Kimi K2.5                          — $0.60/$2.50 per MTok
  Tier 2 — Medium     → Kimi K2.5                          — $0.60/$2.50 per MTok
  Tier 3 — Complex    → Claude Sonnet (upstream default)    — $3/$15 per MTok

Logic phân loại:
  1. Keyword PII/sensitive → Tier 0 (bất kể model client yêu cầu)
  2. Nếu client đã chỉ định model thuộc vnpay-* → giữ nguyên (client override)
  3. Prompt ngắn + keyword đơn giản → Tier 1
  4. Keyword coding/analysis → Tier 2
  5. Default → giữ model client chọn
"""

import re
import logging
import litellm
from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger("vnpay_routing_hook")

# ── Custom model pricing (models chưa có trong LiteLLM built-in cost map) ────
# Ref: https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
# MiniMax-M2 / M2.7 chưa có trong upstream — dùng giá MiniMax-M2 ($0.30/$1.20 per MTok)
_CUSTOM_MODEL_COST = {
    "minimax/MiniMax-M2": {
        "input_cost_per_token": 3e-07,
        "output_cost_per_token": 1.2e-06,
        "max_input_tokens": 1000000,
        "max_output_tokens": 40960,
        "litellm_provider": "minimax",
    },
    "MiniMax-M2": {
        "input_cost_per_token": 3e-07,
        "output_cost_per_token": 1.2e-06,
        "max_input_tokens": 1000000,
        "max_output_tokens": 40960,
        "litellm_provider": "minimax",
    },
    "minimax/MiniMax-M2.7": {
        "input_cost_per_token": 3e-07,
        "output_cost_per_token": 1.2e-06,
        "max_input_tokens": 1000000,
        "max_output_tokens": 16384,
        "litellm_provider": "minimax",
    },
    "MiniMax-M2.7": {
        "input_cost_per_token": 3e-07,
        "output_cost_per_token": 1.2e-06,
        "max_input_tokens": 1000000,
        "max_output_tokens": 16384,
        "litellm_provider": "minimax",
    },
    "openai/minimax": {
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
        "max_input_tokens": 1000000,
        "max_output_tokens": 16384,
        "litellm_provider": "openai",
    },
    "openai/v_minimax": {
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
        "max_input_tokens": 131072,
        "max_output_tokens": 16384,
        "litellm_provider": "openai",
    },
    "openai/v_glm46": {
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
        "max_input_tokens": 128000,
        "max_output_tokens": 16384,
        "litellm_provider": "openai",
    },
    "openai/v_search": {
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
        "max_input_tokens": 8192,
        "max_output_tokens": 0,
        "litellm_provider": "openai",
        "mode": "embedding",
    },
}
for _model, _info in _CUSTOM_MODEL_COST.items():
    litellm.model_cost[_model] = _info
    logger.info(f"[pricing] registered custom cost: {_model}")

# ── Tier 0: Dữ liệu nhạy cảm VNPAY — bắt buộc on-premise ─────────────────
SENSITIVE_PATTERNS = [
    # Dữ liệu tài chính / giao dịch
    r"\b(số thẻ|card.?number|pan\b|cvv|cvc)\b",
    r"\b(otp|mã xác thực|mã pin|pin\b)\b",
    r"\b(số tài khoản|account.?number|stk\b)\b",
    r"\b(dư nợ|dư nợ|số dư|balance)\b",
    r"\b(giao dịch|transaction|thanh toán thực|payment.?data)\b",
    # Dữ liệu khách hàng
    r"\b(cmnd|căn cước|cccd|passport|hộ chiếu)\b",
    r"\b(khách hàng|customer).{0,20}(thực|real|prod|production)\b",
    r"\b(thông tin cá nhân|pii|personal.?info)\b",
    # Source code nội bộ nhạy cảm
    r"\b(secret|private.?key|api.?key|token|credential|password)\s*[=:]\s*\S",
    r"\b(database.?url|connection.?string|dsn)\s*[=:]\s*\S",
    # Prefix tường minh từ client
    r"^\[SENSITIVE\]",
    r"^\[NỘI BỘ\]",
]

# ── Tier 1: Tác vụ đơn giản → MiniMax ────────────────────────────────────
SIMPLE_PATTERNS = [
    r"\b(dịch|translate|translation)\b",
    r"\b(tóm tắt|summarize|summary|tóm lược)\b",
    r"\b(format|reformat|làm sạch|clean.?up)\b",
    r"\b(grammar|ngữ pháp|chính tả|spell.?check)\b",
    r"\b(template|mẫu|fill.?in|điền vào)\b",
]


# ── Tier 2: Tác vụ coding/phân tích → Kimi ───────────────────────────────
MEDIUM_PATTERNS = [
    r"\b(debug|fix.?bug|lỗi|error|exception|traceback)\b",
    r"\b(unit.?test|test.?case|viết test)\b",
    r"\b(code.?review|review.?code|kiểm tra code)\b",
    r"\b(phân tích|analyze|analysis)\b",
    r"\b(refactor|tái cấu trúc|optimize|tối ưu)\b",
    r"\b(explain.?code|giải thích code|đọc hiểu)\b",
    r"\b(sql|query|database)\b",
]

# ── Model names ────────────────────────────────────────────────────────────
MODEL_SENSITIVE = "vnpay-sensitive"   # v_glm46 on-premise (dữ liệu nhạy cảm)
MODEL_SIMPLE    = "vnpay-simple"      # Kimi K2.5 (tác vụ đơn giản)
MODEL_MEDIUM    = "vnpay-medium"      # Kimi K2.5 (coding/analysis)
# Tier 3 = giữ nguyên model client chọn (claude-sonnet, claude-opus, v.v.)

# Routing hook CHỈ override khi model client chọn là Claude default của Anthropic
# (claude-sonnet-4-*, claude-opus-4-*, claude-haiku-4-*, claude-3-*).
# Mọi model khác (VNPay, Kimi, MiniMax, v_glm46, v.v.) → giữ nguyên, không override.
CLAUDE_DEFAULT_PATTERN = re.compile(
    r"^claude-(sonnet|opus|haiku)-(4|3|3-5|3-7)",
    re.IGNORECASE,
)

# ── Team alias mapping: anthropic/claude* → moonshot/kimi-k2.5 ─────────────
# Các team này không được phép dùng Anthropic Claude — mọi request
# tới model anthropic/* hoặc claude-* đều bị redirect sang Kimi K2.5.
TEAM_CLAUDE_TO_KIMI_ALIASES = {
    "DVNH-KCN",     # team_id: b9216f8d-1c55-423a-abcd-f8f4d3c64532
    "DVTT-KCN",     # team_id: 2e043e39-50c7-45b2-8aa8-4d313164fe11
    "GSVH-KCN",     # team_id: adcee45e-9f93-4dd7-b07c-a74e37947478
    "THHT-KCN",     # team_id: 4f1c1a0a-37ef-4dc7-9373-0fee7c87f640
    "TTKHDL-KCN",   # team_id: 205dc6e4-ecf4-435c-b8ed-88a3a3107930
    "UDDD-KCN",     # team_id: 9b86b2a8-a10c-4bfb-8859-a3f9d4ccb1d1
    "eFIN-KCN",     # team_id: 5ee7ab1a-0115-46cb-aca5-e86ac8f13ec6
}

# Match anthropic/* hoặc claude-* hoặc claude/* (mọi variant)
ANTHROPIC_MODEL_PATTERN = re.compile(
    r"^(anthropic/|claude[-/])",
    re.IGNORECASE,
)
MODEL_KIMI = "moonshot/kimi-k2.5"


def _sanitize_tool_messages(messages: list[dict]) -> list[dict]:
    """
    Strip orphan tool_calls từ conversation history.

    Kimi K2.5 (và nhiều model khác) yêu cầu mọi tool_call_id trong assistant
    message phải có tool response message tương ứng ngay sau đó. Khi client
    truncate history (e.g. context window), tool response có thể bị mất →
    400 "tool_call_id is not found".

    Logic:
      1. Thu thập tất cả tool_call_id có response (role=tool)
      2. Với mỗi assistant message có tool_calls, loại bỏ các call không có response
      3. Nếu assistant message mất hết tool_calls → xóa luôn message đó
    """
    if not messages:
        return messages

    # Collect all tool_call_ids that have a matching tool response
    responded_ids: set[str] = set()
    for m in messages:
        if m.get("role") == "tool" and "tool_call_id" in m:
            responded_ids.add(m["tool_call_id"])

    sanitized = []
    removed_count = 0
    for m in messages:
        tool_calls = m.get("tool_calls")
        if m.get("role") == "assistant" and tool_calls and isinstance(tool_calls, list):
            # Keep only tool_calls that have matching responses
            valid_calls = [tc for tc in tool_calls if tc.get("id") in responded_ids]
            orphan_count = len(tool_calls) - len(valid_calls)
            if orphan_count > 0:
                removed_count += orphan_count
                if valid_calls:
                    # Some calls still valid — keep message with filtered calls
                    m = {**m, "tool_calls": valid_calls}
                elif m.get("content"):
                    # No valid calls but has text content — keep without tool_calls
                    m = {k: v for k, v in m.items() if k != "tool_calls"}
                else:
                    # No valid calls, no content — drop entire message
                    continue
        # Drop orphan tool responses (no matching tool_call in any assistant message)
        if m.get("role") == "tool" and "tool_call_id" in m:
            # Check if any assistant message in sanitized list has this call
            has_parent = False
            for prev in sanitized:
                if prev.get("role") == "assistant":
                    for tc in (prev.get("tool_calls") or []):
                        if tc.get("id") == m["tool_call_id"]:
                            has_parent = True
                            break
                if has_parent:
                    break
            if not has_parent:
                removed_count += 1
                continue
        sanitized.append(m)

    if removed_count > 0:
        logger.info(f"[sanitize] removed {removed_count} orphan tool_call(s)/response(s)")
    return sanitized


def _extract_prompt(data: dict) -> str:
    """Gộp tất cả message content thành 1 string để match pattern."""
    messages = data.get("messages", [])
    parts = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            # multimodal: lấy phần text
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return " ".join(parts)


def _match_any(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower, re.IGNORECASE) for p in patterns)


class VNPayRoutingHook(CustomLogger):
    """
    LiteLLM CustomLogger — chỉ dùng async_pre_call_hook.
    Được đăng ký qua litellm_settings.callbacks trong config.yaml.
    """

    _pricing_injected = False

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict,
        call_type: str,
    ) -> dict:
        # ── Lazy inject custom pricing (chạy 1 lần duy nhất) ─────────────
        if not VNPayRoutingHook._pricing_injected:
            for model, info in _CUSTOM_MODEL_COST.items():
                litellm.model_cost[model] = info
            VNPayRoutingHook._pricing_injected = True
            logger.info(f"[pricing] registered {len(_CUSTOM_MODEL_COST)} custom models")

        current_model = data.get("model", "")

        # ── Team alias: anthropic/claude* → moonshot/kimi-k2.5 ─────────────
        # Áp dụng trước mọi logic khác — nếu team bị restrict, không cho phép
        # gọi bất kỳ model Claude/Anthropic nào dù client chỉ định tường minh.
        team_alias = getattr(user_api_key_dict, "team_alias", None) or ""
        if team_alias in TEAM_CLAUDE_TO_KIMI_ALIASES:
            if ANTHROPIC_MODEL_PATTERN.match(current_model):
                logger.info(
                    f"[routing] team={team_alias} → redirect {current_model} → {MODEL_KIMI} (team alias rule)"
                )
                data["model"] = MODEL_KIMI
                data.setdefault("metadata", {})["routing_reason"] = f"team_alias:{team_alias}"
                current_model = MODEL_KIMI

        # ── MiniMax: strip unsupported fields + ensure max_tokens ───────────
        MINIMAX_MODELS = {"vnpay/minimax", "openai/minimax", "MiniMax-M2.7", "minimax"}
        MINIMAX_DEFAULT_MAX_TOKENS = 16384
        if current_model in MINIMAX_MODELS or "minimax" in current_model.lower():
            if "output_config" in data:
                data.pop("output_config", None)
                logger.info("[routing] stripped output_config for MiniMax")
            # Ensure max_tokens đủ lớn — MiniMax M2.7 hỗ trợ thinking,
            # reasoning tokens ăn budget → output bị cắt nếu max_tokens thấp
            current_max = data.get("max_tokens") or data.get("max_completion_tokens")
            if not current_max or current_max < MINIMAX_DEFAULT_MAX_TOKENS:
                logger.info(f"[routing] minimax → set max_tokens={MINIMAX_DEFAULT_MAX_TOKENS} (was: {current_max})")
                data["max_tokens"] = MINIMAX_DEFAULT_MAX_TOKENS

        # ── Kimi K2.5 (reasoning model): force temperature=1 ────────────────
        # Moonshot API chỉ chấp nhận temperature=1 cho reasoning models.
        # Client có thể gửi bất kỳ giá trị nào → override tại đây trước khi
        # request đến LiteLLM router, tránh "invalid temperature" 400 error.
        KIMI_MODELS = {"vnpay-simple", "vnpay-medium", "moonshot/kimi-k2.5", "kimi-k2.5"}
        KIMI_DEFAULT_MAX_TOKENS = 16384  # 16K — đủ cho reasoning + answer
        if current_model in KIMI_MODELS or "kimi-k2" in current_model.lower():
            if data.get("temperature") != 1:
                logger.info(f"[routing] kimi reasoning model → force temperature=1 (was: {data.get('temperature')})")
                data["temperature"] = 1
            # Ensure max_tokens đủ lớn cho reasoning model — Kimi K2.5 dùng
            # reasoning tokens (thinking) + text tokens. Nếu max_tokens quá thấp
            # (e.g. 8192 default), reasoning ăn hết budget → output bị cắt.
            current_max = data.get("max_tokens") or data.get("max_completion_tokens")
            if not current_max or current_max < KIMI_DEFAULT_MAX_TOKENS:
                logger.info(f"[routing] kimi → set max_tokens={KIMI_DEFAULT_MAX_TOKENS} (was: {current_max})")
                data["max_tokens"] = KIMI_DEFAULT_MAX_TOKENS
            # Sanitize orphan tool_calls — Kimi yêu cầu mọi tool_call_id phải
            # có tool response. Client truncate history → 400 error.
            messages = data.get("messages")
            if messages:
                data["messages"] = _sanitize_tool_messages(messages)

        # Chỉ override khi model là Claude default (claude-sonnet-4-*, claude-opus-4-*, v.v.)
        # Mọi model khác → client đã chủ động chọn → tôn trọng, không override.
        if not CLAUDE_DEFAULT_PATTERN.match(current_model):
            logger.debug(f"[routing] non-claude-default → keeping {current_model}")
            return data

        prompt = _extract_prompt(data)
        if not prompt:
            return data

        # ── Tier 0: Sensitive → on-premise bất kể ─────────────────────────
        if _match_any(prompt, SENSITIVE_PATTERNS):
            logger.info(f"[routing] SENSITIVE detected → {MODEL_SENSITIVE} (was: {current_model})")
            data["model"] = MODEL_SENSITIVE
            # Gắn metadata để audit log biết lý do
            data.setdefault("metadata", {})["routing_reason"] = "sensitive"
            return data

        # ── Tier 1: Simple → on-premise (v_glm46) ─────────────────────────
        if _match_any(prompt, SIMPLE_PATTERNS):
            logger.info(f"[routing] SIMPLE detected → {MODEL_SIMPLE} (was: {current_model})")
            data["model"] = MODEL_SIMPLE
            data.setdefault("metadata", {})["routing_reason"] = "simple"
            return data

        # ── Tier 2: Coding/analysis → Kimi ────────────────────────────────
        if _match_any(prompt, MEDIUM_PATTERNS):
            logger.info(f"[routing] MEDIUM detected → {MODEL_MEDIUM} (was: {current_model})")
            data["model"] = MODEL_MEDIUM
            data.setdefault("metadata", {})["routing_reason"] = "medium"
            return data

        # ── Tier 3: Giữ nguyên model client chọn (Claude, v.v.) ───────────
        logger.debug(f"[routing] COMPLEX/default → keeping {current_model}")
        data.setdefault("metadata", {})["routing_reason"] = "complex_passthrough"
        return data


# Đăng ký instance — LiteLLM import module này và dùng object này
vnpay_routing_hook = VNPayRoutingHook()
