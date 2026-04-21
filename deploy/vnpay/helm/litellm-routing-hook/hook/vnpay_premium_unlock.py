"""
VNPay OSS Patches — unlock premium gates + fix upstream bugs
=============================================================

Gộp các patch module-level cho LiteLLM OSS khi self-host không có
LITELLM_LICENSE. Mỗi patch chạy 1 lần lúc module load (callback này được
register qua litellm_settings.callbacks, load sau khi proxy_server import xong).

Patches:
  1. premium_user override → True
     `litellm.proxy.proxy_server.premium_user` set từ `_license_check.is_premium()`.
     Force True để unlock audit log DB writes, endpoint /audit (enterprise
     package), UI Audit Logs gate (qua JWT, xem vnpay_sso_handler.py), và
     các enterprise feature khác. `create_audit_log_for_update` late-import
     `premium_user` mỗi lần chạy nên sẽ nhận True.

  2. _authorize_and_filter_teams admin bypass
     Upstream bug: /team/list?user_id=X với caller proxy_admin trả 0 team
     (team_endpoints.py:3645 filter by membership bất kể role). UI dialog
     Policy Attachment / các dropdown team luôn truyền userId → admin dropdown
     rỗng. Patch: nếu caller là proxy_admin → trả tất cả teams, skip
     membership filter. Non-admin giữ nguyên logic gốc.

Yêu cầu pair:
  - Đăng ký vào litellm_settings.callbacks:
      /etc/litellm/hooks/vnpay_premium_unlock.vnpay_premium_unlock
  - Thêm `store_audit_logs: true` vào litellm_settings (patch #1 dependency).
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


def _patch_team_list_admin_filter() -> None:
    """
    Fix upstream bug: /team/list?user_id=self với proxy_admin trả 0 team.

    Upstream `_authorize_and_filter_teams` (team_endpoints.py) không phân
    biệt admin với non-admin khi user_id được truyền → fall vào branch
    `elif user_id:` filter theo membership. Admin thuộc 0 team → dropdown
    UI Policy Attachment rỗng.

    Patch: admin → trả tất cả teams, bỏ qua user_id filter. `list_team`
    resolve `_authorize_and_filter_teams` tại call time (global lookup)
    nên setattr module-level sẽ có hiệu lực cho mọi request sau đó.
    """
    from litellm.proxy.management_endpoints import team_endpoints as _te

    _original = _te._authorize_and_filter_teams

    async def _patched(
        user_api_key_dict,
        user_id,
        prisma_client,
        user_api_key_cache,
        proxy_logging_obj,
    ):
        if _te._user_has_admin_view(user_api_key_dict):
            return list(
                await prisma_client.db.litellm_teamtable.find_many(
                    include={"litellm_model_table": True}
                )
            )
        return await _original(
            user_api_key_dict=user_api_key_dict,
            user_id=user_id,
            prisma_client=prisma_client,
            user_api_key_cache=user_api_key_cache,
            proxy_logging_obj=proxy_logging_obj,
        )

    _te._authorize_and_filter_teams = _patched
    logger.warning(
        "[vnpay] _authorize_and_filter_teams patched: proxy_admin luôn trả "
        "all teams (bypass user_id membership filter)"
    )


_unlock_premium()
_patch_team_list_admin_filter()


class VNPayPremiumUnlock(CustomLogger):
    """No-op CustomLogger — side effects happen at module import time."""

    pass


vnpay_premium_unlock = VNPayPremiumUnlock()
