"""
VNPay Premium Unlock — bypass OSS license gates
================================================

LiteLLM OSS chặn audit log DB writes, allowed_ips middleware, DOCS_TITLE
enterprise, v.v. qua biến global `premium_user` trong
`litellm.proxy.proxy_server` (set từ `_license_check.is_premium()`).

VNPay self-host OSS không có LITELLM_LICENSE, nên ta force `premium_user = True`
tại module load — callback này chạy sau khi proxy_server đã import xong.
`create_audit_log_for_update` late-import `premium_user` mỗi lần chạy nên sẽ
thấy giá trị True và tiếp tục ghi xuống `LiteLLM_AuditLog`.

Yêu cầu pair:
  - Đăng ký vào litellm_settings.callbacks:
      /etc/litellm/hooks/vnpay_premium_unlock.vnpay_premium_unlock
  - Thêm `store_audit_logs: true` vào litellm_settings
    (flag riêng, không phụ thuộc premium_user).
"""

import logging

from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy import proxy_server

logger = logging.getLogger("vnpay_premium_unlock")


def _unlock_premium() -> None:
    previous = getattr(proxy_server, "premium_user", None)
    proxy_server.premium_user = True
    logger.warning(
        "[vnpay] premium_user override applied (was=%s, now=True). "
        "Audit log DB writes enabled.",
        previous,
    )


_unlock_premium()


class VNPayPremiumUnlock(CustomLogger):
    """No-op CustomLogger — side effect happens at module import time."""

    pass


vnpay_premium_unlock = VNPayPremiumUnlock()
