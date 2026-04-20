"""
VNPay Splunk Audit Exporter
============================

Push LiteLLM audit log events sang Splunk HEC (HTTP Event Collector) real-time.
LiteLLM dispatch qua `litellm.audit_log_callbacks` → gọi
`async_log_audit_log_event(StandardAuditLogPayload)` trong background task.

Env:
  SPLUNK_HEC_URL         https://splunk.vnpay.vn:8088/services/collector
  SPLUNK_HEC_TOKEN       HEC token (inject qua secret `litellm-splunk-hec`)
  SPLUNK_HEC_INDEX       default "litellm_audit"
  SPLUNK_HEC_SOURCETYPE  default "_json"
  SPLUNK_HEC_VERIFY_TLS  "false" để tắt cert verify (default true)

Nếu URL hoặc TOKEN thiếu → exporter tự disable (log WARNING, không break proxy).

Đăng ký:
  litellm_settings:
    store_audit_logs: true
    audit_log_callbacks:
      - /etc/litellm/hooks/vnpay_splunk_audit.vnpay_splunk_audit
"""

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from litellm.integrations.custom_logger import CustomLogger

if TYPE_CHECKING:
    from litellm.types.utils import StandardAuditLogPayload

logger = logging.getLogger("vnpay_splunk_audit")


def _iso_to_epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc).timestamp()


class VNPaySplunkAudit(CustomLogger):
    def __init__(self) -> None:
        self.url = os.getenv("SPLUNK_HEC_URL", "").strip()
        self.token = os.getenv("SPLUNK_HEC_TOKEN", "").strip()
        self.index = os.getenv("SPLUNK_HEC_INDEX", "litellm_audit")
        self.sourcetype = os.getenv("SPLUNK_HEC_SOURCETYPE", "_json")
        verify_tls = os.getenv("SPLUNK_HEC_VERIFY_TLS", "true").lower() != "false"
        self.host = os.getenv("HOSTNAME", "litellm-proxy")

        self._enabled = bool(self.url and self.token)
        if not self._enabled:
            logger.warning(
                "[vnpay-splunk-audit] disabled — SPLUNK_HEC_URL or "
                "SPLUNK_HEC_TOKEN not set"
            )
            self._client = None
            return

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0),
            verify=verify_tls,
            headers={"Authorization": f"Splunk {self.token}"},
        )
        logger.info(
            "[vnpay-splunk-audit] enabled → %s (index=%s)", self.url, self.index
        )

    async def async_log_audit_log_event(
        self, audit_log: "StandardAuditLogPayload"
    ) -> None:
        if not self._enabled or self._client is None:
            return
        event = {
            "time": _iso_to_epoch(audit_log.get("updated_at", "")),
            "host": self.host,
            "source": "litellm",
            "sourcetype": self.sourcetype,
            "index": self.index,
            "event": dict(audit_log),
        }
        try:
            resp = await self._client.post(self.url, json=event)
            resp.raise_for_status()
        except Exception as e:
            logger.error(
                "[vnpay-splunk-audit] HEC post failed id=%s action=%s table=%s: %s",
                audit_log.get("id"),
                audit_log.get("action"),
                audit_log.get("table_name"),
                e,
            )


vnpay_splunk_audit = VNPaySplunkAudit()
