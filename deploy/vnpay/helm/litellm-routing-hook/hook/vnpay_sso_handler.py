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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_logger = logging.getLogger("vnpay_sso")

LITELLM_UI_SESSION_DURATION = "8h"
LITELLM_UI_SESSION_MAX_AGE = 8 * 3600  # giây — phải khớp LITELLM_UI_SESSION_DURATION
ALLOWED_DOMAIN = "@vnpay.vn"

# ── Audit log actions (custom, chấp nhận bởi schema — action là text NOT NULL) ──
# upstream chỉ dùng created/updated/deleted/blocked/rotated/regenerated/unblocked.
# SSO flow thêm login/login_rejected/login_failed để track authentication.
_AUDIT_LOGIN_OK = "login"
_AUDIT_LOGIN_REJECTED = "login_rejected"
_AUDIT_LOGIN_FAILED = "login_failed"
_AUDIT_TABLE_SSO = "SSO_Session"


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


async def _user_exists(email: str) -> bool:
    """Check user có trong LiteLLM_UserTable chưa — để phân biệt first-SSO-login
    (cần emit `UserTable created` audit) vs re-login (chỉ emit session key).
    """
    try:
        from litellm.proxy.proxy_server import prisma_client
        if prisma_client is None:
            return False
        user = await prisma_client.db.litellm_usertable.find_unique(
            where={"user_id": email}
        )
        return user is not None
    except Exception as exc:
        _logger.warning("user_exists check failed for %s: %s", email, exc)
        return False


async def _emit_audit(
    changed_by: str,
    action: str,
    table_name: str,
    object_id: str,
    updated_values: Optional[Dict[str, Any]] = None,
    before_value: Optional[Dict[str, Any]] = None,
) -> None:
    """Fire-and-forget audit emission — write trực tiếp Prisma + manual dispatch
    tới audit_log_callbacks (Splunk HEC qua vnpay_splunk_audit).

    Bypass `create_audit_log_for_update` của upstream vì 2 lý do:
    (1) Pydantic `LiteLLM_AuditLogs` restrict action ∈ {created,updated,deleted,
        blocked,unblocked,rotated} và table_name ∈ 6 tên cứng → không cho
        "login"/"login_rejected"/"login_failed" hoặc table "SSO_Session".
    (2) `premium_user` bị reassign về False sau startup (proxy_server lines 813,
        2920, 3460 re-check `_license_check.is_premium()`) → `vnpay_premium_unlock`
        override không bền → upstream gate trả sớm.

    DB schema (`action text NOT NULL`) tự do hơn Pydantic → write raw qua
    Prisma thoải mái. Không raise — audit failure không được break login flow.
    """
    try:
        from litellm.proxy.proxy_server import prisma_client
        if prisma_client is None:
            _logger.warning("audit skip: prisma_client is None")
            return

        import json
        # Prisma client refuse explicit None cho jsonb fields → chỉ set key
        # khi value thực sự có. Empty dict/None → omit field hoàn toàn.
        data = {
            "id": str(uuid.uuid4()),
            "updated_at": datetime.now(timezone.utc),
            "changed_by": changed_by,
            "changed_by_api_key": "sso",
            "table_name": table_name,
            "object_id": object_id,
            "action": action,
        }
        if before_value:
            data["before_value"] = json.dumps(before_value)
        if updated_values:
            data["updated_values"] = json.dumps(updated_values)
        await prisma_client.db.litellm_auditlog.create(data=data)

        # Dispatch tới audit_log_callbacks (Splunk, nếu enabled). Best-effort.
        try:
            import litellm
            for cb in getattr(litellm, "audit_log_callbacks", None) or []:
                if isinstance(cb, str):
                    continue  # string reference chưa resolve — skip
                logger_fn = getattr(cb, "async_log_audit_log_event", None)
                if logger_fn is not None:
                    await logger_fn({
                        **data,
                        "updated_at": data["updated_at"].isoformat(),
                    })
        except Exception as dispatch_exc:
            _logger.warning("audit callback dispatch failed: %s", dispatch_exc)
    except Exception as exc:
        _logger.warning(
            "audit emit failed (action=%s table=%s): %s", action, table_name, exc
        )


async def _make_ui_session(email: str, login_method: str) -> str:
    """Tạo LiteLLM key + JWT cho UI session. Return jwt_token string.

    Flow:
    1. Xoá SSO keys cũ của user (pattern "UI SSO: {email}")
    2. Tạo key mới qua `generate_key_helper_fn` (trả raw `sk-xxx` cho Bearer)
    3. Encode JWT cookie chứa raw token để UI extract + gửi Bearer header
    4. Emit audit events: UserTable created (new user), VerificationToken
       created (session key), SSO_Session login (summary cho Splunk filter).

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
    was_new_user = not await _user_exists(email)

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

    # ── Audit events (upstream generate_key_helper_fn không emit audit khi
    # gọi từ context không phải HTTP endpoint → phải emit tay) ──
    # IMPORTANT: key_data["token"] = raw "sk-xxx" (cho Bearer auth). DB
    # lưu HASH của key. Audit object_id phải là hash để match convention
    # và tránh leak raw credential vào audit log.
    raw_key = key_data.get("token", "")
    try:
        from litellm.proxy.utils import hash_token
        token_hash = hash_token(raw_key) if raw_key else ""
    except Exception:
        token_hash = key_data.get("token_id", "") or ""
    if was_new_user:
        await _emit_audit(
            changed_by=email,
            action="created",
            table_name="LiteLLM_UserTable",
            object_id=email,
            updated_values={
                "user_email": email,
                "user_role": user_role,
                "login_method": login_method,
                "auto_provisioned_by_sso": True,
            },
        )
    await _emit_audit(
        changed_by=email,
        action="created",
        table_name="LiteLLM_VerificationToken",
        object_id=token_hash,
        updated_values={
            "key_alias": f"UI SSO: {email}",
            "user_id": email,
            "team_id": team_id,
            "user_role": user_role,
            "duration": LITELLM_UI_SESSION_DURATION,
            "login_method": login_method,
        },
    )
    await _emit_audit(
        changed_by=email,
        action=_AUDIT_LOGIN_OK,
        table_name=_AUDIT_TABLE_SSO,
        object_id=token_hash,
        updated_values={
            "email": email,
            "login_method": login_method,
            "user_role": user_role,
            "team_id": team_id,
            "is_new_user": was_new_user,
            "session_duration": LITELLM_UI_SESSION_DURATION,
        },
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
                await _emit_audit(
                    changed_by=email or "(unknown)",
                    action=_AUDIT_LOGIN_REJECTED,
                    table_name=_AUDIT_TABLE_SSO,
                    object_id=email or "(unknown)",
                    updated_values={
                        "email": email or None,
                        "login_method": "teleport",
                        "reason": "domain_not_allowed" if email else "jwt_missing_or_invalid",
                        "allowed_domain": ALLOWED_DOMAIN,
                    },
                )
                return RedirectResponse("/ui", status_code=302)

            try:
                jwt_token = await _make_ui_session(email, login_method="teleport")
                _logger.info("Teleport SSO: session created for %s", email)
                # Match LiteLLM native flow: cookie-only handoff, `?login=success`
                # flag triggers UI to read cookie. Avoid token in URL (race: UI may
                # fire /models before useEffect extracts URL token → Bearer undefined).
                response = RedirectResponse("/ui/?login=success", status_code=303)
                # Max-Age khớp TTL token (8h). Thiếu Max-Age → browser giữ cookie
                # vô hạn, token backend expire nhưng UI vẫn gửi cookie cũ → loạt XHR
                # 401 trên /key/list, /team/list... UI render "0 results" thay vì
                # redirect SSO (nginx handoff rule chỉ trigger khi cookie='').
                response.set_cookie(
                    key="token",
                    value=jwt_token,
                    max_age=LITELLM_UI_SESSION_MAX_AGE,
                    # httponly=False — UI đọc cookie qua JS để inject Bearer header.
                    secure=True,
                    samesite="lax",
                )
                return response
            except Exception as exc:
                _logger.error("Teleport SSO: session error for %s: %s", email, exc)
                await _emit_audit(
                    changed_by=email,
                    action=_AUDIT_LOGIN_FAILED,
                    table_name=_AUDIT_TABLE_SSO,
                    object_id=email,
                    updated_values={
                        "email": email,
                        "login_method": "teleport",
                        "error": str(exc)[:500],
                    },
                )
                return RedirectResponse("/ui", status_code=302)

        _logger.info("VNPay SSO: /teleport-sso route registered")

        # ── /vnpay-sso — oauth2-proxy flow (fallback) ─────────────────────────────
        @app.get("/vnpay-sso", include_in_schema=False)
        async def vnpay_sso_login(request: Request):
            email = request.headers.get("X-Auth-Request-Email", "").strip().lower()

            if not email.endswith(ALLOWED_DOMAIN):
                _logger.warning("oauth2-proxy SSO: rejected '%s'", email)
                await _emit_audit(
                    changed_by=email or "(unknown)",
                    action=_AUDIT_LOGIN_REJECTED,
                    table_name=_AUDIT_TABLE_SSO,
                    object_id=email or "(unknown)",
                    updated_values={
                        "email": email or None,
                        "login_method": "oauth2_proxy",
                        "reason": "domain_not_allowed" if email else "header_missing",
                        "allowed_domain": ALLOWED_DOMAIN,
                    },
                )
                return RedirectResponse("/oauth2/sign_out", status_code=302)

            try:
                jwt_token = await _make_ui_session(email, login_method="oauth2_proxy")
                _logger.info("oauth2-proxy SSO: session created for %s", email)
                response = RedirectResponse("/ui/?login=success", status_code=303)
                response.set_cookie(
                    key="token",
                    value=jwt_token,
                    max_age=LITELLM_UI_SESSION_MAX_AGE,
                    # httponly=False — UI đọc cookie qua JS để inject Bearer header.
                    secure=True,
                    samesite="lax",
                )
                return response
            except Exception as exc:
                _logger.error("oauth2-proxy SSO: session error for %s: %s", email, exc)
                await _emit_audit(
                    changed_by=email,
                    action=_AUDIT_LOGIN_FAILED,
                    table_name=_AUDIT_TABLE_SSO,
                    object_id=email,
                    updated_values={
                        "email": email,
                        "login_method": "oauth2_proxy",
                        "error": str(exc)[:500],
                    },
                )
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
