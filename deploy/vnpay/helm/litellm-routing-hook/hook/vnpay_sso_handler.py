"""
VNPay SSO handler — hỗ trợ hai flow:

Flow 1 — Teleport App Access (litellm.x.vnshop.cloud qua Teleport):
  Browser → Teleport auth (Google SSO) → Teleport proxy với Teleport-Jwt-Assertion header
  → /teleport-sso (Teleport app rewrite redirect target)
  → đọc JWT → tạo LiteLLM session → redirect /ui/?token=...

Flow 2 — oauth2-proxy (fallback, không qua Teleport):
  Browser → nginx auth_request → oauth2-proxy → /vnpay-sso
  → đọc X-Auth-Request-Email → tạo LiteLLM session → redirect /ui/?token=...

custom_sso fallback: vnpay_sso_handler.vnpay_google_sso
"""

import base64
import json
import logging

_logger = logging.getLogger("vnpay_sso")

LITELLM_UI_SESSION_DURATION = "8h"
ALLOWED_DOMAIN = "@vnpay.vn"


def _extract_teleport_email(jwt_str: str) -> str:
    """Decode Teleport-Jwt-Assertion payload (no sig verify — trusted internal Teleport proxy)."""
    try:
        payload_b64 = jwt_str.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        # Teleport claims: traits.email[] → username → sub
        traits = claims.get("traits", {})
        email = (
            (traits.get("email") or [""])[0]
            or claims.get("username", "")
            or claims.get("sub", "")
        )
        return email.strip().lower()
    except Exception:
        return ""


async def _lookup_user_role(email: str) -> str:
    """Query existing user_role from LiteLLM_UserTable. Default app_user if not found."""
    try:
        from litellm.proxy.proxy_server import prisma_client
        if prisma_client is None:
            return "app_user"
        user = await prisma_client.db.litellm_usertable.find_unique(
            where={"user_id": email}
        )
        if user and getattr(user, "user_role", None):
            return user.user_role
    except Exception as exc:
        _logger.warning("user role lookup failed for %s: %s", email, exc)
    return "app_user"


async def _lookup_user_primary_team(email: str) -> str:
    """Return user's first team_id. Fallback litellm-dashboard nếu chưa có team.

    LiteLLM's `generate_key_helper_fn` tạo key với `team_id` + `models=[]` sẽ
    rơi vào trạng thái `no-default-models` nếu team không có models assign.
    Team `litellm-dashboard` (default UI team) không có model list → key
    không gọi được model nào → user nhận 401.

    Fix: set team_id = team thực của user (ví dụ DVTT-KCN với
    `all-proxy-models`). LiteLLM sẽ resolve model access qua team's models.
    """
    try:
        from litellm.proxy.proxy_server import prisma_client
        if prisma_client is None:
            return "litellm-dashboard"
        user = await prisma_client.db.litellm_usertable.find_unique(
            where={"user_id": email}
        )
        teams = getattr(user, "teams", None) if user else None
        if teams:
            return teams[0]
    except Exception as exc:
        _logger.warning("user team lookup failed for %s: %s", email, exc)
    return "litellm-dashboard"


async def _delete_old_sso_keys(email: str) -> int:
    """Xoá toàn bộ SSO session keys cũ của user trước khi tạo key mới.

    Reuse không khả thi (raw `sk-xxx` chỉ tồn tại ở create time, DB lưu
    hash one-way). Thay vào đó: mỗi login → xoá keys cũ + tạo mới. Đảm
    bảo 1 key / user / mọi thời điểm → DB không phình, UI không rối.

    Trade-off: user mở session B trên device khác sẽ kick session A
    (cookie A trỏ key đã xoá). Thực tế user thường login 1 device tại
    một thời điểm; re-login mất ~2s qua SSO.
    """
    try:
        from litellm.proxy.proxy_server import prisma_client
        if prisma_client is None:
            return 0
        result = await prisma_client.db.litellm_verificationtoken.delete_many(
            where={
                "user_id": email,
                "key_alias": f"UI SSO: {email}",
            }
        )
        return int(result) if result else 0
    except Exception as exc:
        _logger.warning("old SSO keys cleanup failed for %s: %s", email, exc)
        return 0


async def _make_ui_session(email: str) -> str:
    """Tạo LiteLLM key + JWT cho UI session. Return jwt_token string.

    Flow:
    1. Xoá SSO keys cũ của user (pattern "UI SSO: {email}")
    2. Tạo key mới qua `generate_key_helper_fn` (trả raw `sk-xxx` cho Bearer)
    3. Encode JWT cookie chứa raw token để UI extract + gửi Bearer header

    Lý do xoá thay vì reuse: DB chỉ lưu HASH của `sk-xxx`, không phục hồi
    được raw token ở login sau. Mỗi login = key mới, xoá cũ → 1 key/user.
    """
    import litellm
    import jwt as pyjwt
    from litellm.proxy.proxy_server import master_key
    from litellm.proxy.management_endpoints.key_management_endpoints import (
        generate_key_helper_fn,
    )

    user_role = await _lookup_user_role(email)
    team_id = await _lookup_user_primary_team(email)

    deleted = await _delete_old_sso_keys(email)
    if deleted:
        _logger.info("SSO: deleted %d old keys for %s before re-creating", deleted, email)

    key_data = await generate_key_helper_fn(
        request_type="user",
        duration=LITELLM_UI_SESSION_DURATION,
        models=[],
        aliases={},
        config={},
        spend=0,
        user_id=email,
        user_email=email,
        user_role=user_role,
        team_id=team_id,
        max_budget=litellm.max_ui_session_budget,
        key_alias=f"UI SSO: {email}",
    )

    # Field names MUST match litellm.types.proxy.ui_sso.ReturnedUITokenObject
    # (key not id — backend auth reads jwt["key"] to look up the API token)
    return pyjwt.encode(
        {
            "user_id": email,
            "key": key_data.get("token", ""),
            "user_email": email,
            "user_role": user_role,
            "login_method": "sso",
            # UI decode JWT cookie để gate Audit Logs / Enterprise pages qua
            # field này. Phải True để khớp với backend override trong
            # vnpay_premium_unlock.py (set proxy_server.premium_user=True).
            # Nếu False → UI hiện "Enterprise Feature" banner dù backend mở.
            "premium_user": True,
            "auth_header_name": "Authorization",
            "disabled_non_admin_personal_key_creation": False,
            "server_root_path": "",
        },
        master_key or "",
        algorithm="HS256",
    )


def _register_routes() -> None:
    try:
        from litellm.proxy.proxy_server import app
        from fastapi import Request
        from fastapi.responses import RedirectResponse

        # ── /teleport-sso — Teleport App Access flow ──────────────────────────────
        # Teleport inject Teleport-Jwt-Assertion header sau khi user đã auth qua Google.
        # Cần cấu hình Teleport app rewrite.redirect: /teleport-sso
        @app.api_route("/teleport-sso", methods=["GET", "POST", "HEAD"], include_in_schema=False)
        async def teleport_sso_login(request: Request):
            # CRITICAL: HEAD = Teleport health probe (gửi mỗi ~30s). KHÔNG được
            # trigger _make_ui_session vì handler sẽ delete keys cũ + tạo key
            # mới → cookie user đang active bị invalidate → 401 storm.
            # HEAD chỉ cần return 303 để Teleport biết endpoint sống.
            if request.method == "HEAD":
                return RedirectResponse("/ui/?login=success", status_code=303)

            jwt_str = request.headers.get("Teleport-Jwt-Assertion", "")
            email = _extract_teleport_email(jwt_str) if jwt_str else ""

            if not email.endswith(ALLOWED_DOMAIN):
                _logger.warning("Teleport SSO: rejected email='%s'", email or "(none)")
                return RedirectResponse("/ui", status_code=302)

            try:
                jwt_token = await _make_ui_session(email)
                _logger.info("Teleport SSO: session created for %s", email)
                # Match LiteLLM native flow: cookie-only handoff, `?login=success`
                # flag triggers UI to read cookie. Avoid token in URL (race: UI may
                # fire /models before useEffect extracts URL token → Bearer undefined).
                response = RedirectResponse("/ui/?login=success", status_code=303)
                response.set_cookie(key="token", value=jwt_token)
                return response
            except Exception as exc:
                _logger.error("Teleport SSO: session error for %s: %s", email, exc)
                return RedirectResponse("/ui", status_code=302)

        _logger.info("VNPay SSO: /teleport-sso route registered")

        # ── /vnpay-sso — oauth2-proxy flow (fallback) ─────────────────────────────
        @app.get("/vnpay-sso", include_in_schema=False)
        async def vnpay_sso_login(request: Request):
            email = request.headers.get("X-Auth-Request-Email", "").strip().lower()

            if not email.endswith(ALLOWED_DOMAIN):
                _logger.warning("oauth2-proxy SSO: rejected '%s'", email)
                return RedirectResponse("/oauth2/sign_out", status_code=302)

            try:
                jwt_token = await _make_ui_session(email)
                _logger.info("oauth2-proxy SSO: session created for %s", email)
                response = RedirectResponse("/ui/?login=success", status_code=303)
                response.set_cookie(key="token", value=jwt_token)
                return response
            except Exception as exc:
                _logger.error("oauth2-proxy SSO: session error for %s: %s", email, exc)
                return RedirectResponse("/oauth2/sign_out", status_code=302)

        _logger.info("VNPay SSO: /vnpay-sso route registered")

    except Exception as exc:
        _logger.warning("VNPay SSO: could not register routes: %s", exc)


_register_routes()


# ── custom_sso hook (fallback nếu /sso/callback được trigger) ─────────────────
async def vnpay_google_sso(result):
    """Fallback custom_sso cho trường hợp LiteLLM trigger /sso/callback."""
    from litellm.proxy._types import SSOUserDefinedValues

    email = (
        getattr(result, "email", None)
        or getattr(result, "preferred_username", None)
        or ""
    ).strip().lower()

    user_role = await _lookup_user_role(email) if email else "app_user"

    return SSOUserDefinedValues(
        models=[],
        user_id=email or "unknown",
        user_email=email or None,
        user_role=user_role,
        max_budget=None,
        budget_duration=None,
    )
