from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.schemas import ObserverStatusResponse


class ObserverGatewayError(RuntimeError):
    """Raised when the WhatsApp gateway is unavailable or returns invalid data."""


class ObserverGatewayService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def connect_observer(self) -> ObserverStatusResponse:
        payload = await self._request("POST", "/internal/observer/connect")
        return self._build_status(payload)

    async def get_observer_status(self, *, refresh_qr: bool = False) -> ObserverStatusResponse:
        if refresh_qr:
            return await self.connect_observer()

        payload = await self._request("GET", "/internal/observer/status")
        return self._build_status(payload)

    async def _request(self, method: str, path: str) -> dict[str, Any]:
        headers = {"x-internal-api-token": self.settings.internal_api_token}
        timeout = self.settings.request_timeout_seconds

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_whatsapp_gateway_url,
            timeout=timeout,
            headers=headers,
        ) as client:
            response = await client.request(method, path)

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected gateway error."
            raise ObserverGatewayError(
                f"WhatsApp gateway request failed ({response.status_code}) on {path}: {detail}"
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise ObserverGatewayError(f"WhatsApp gateway returned an invalid payload on {path}.")

        return payload

    def _build_status(self, payload: dict[str, Any]) -> ObserverStatusResponse:
        return ObserverStatusResponse(
            instance_name=str(payload.get("instance_name") or "observer"),
            connected=bool(payload.get("connected")),
            state=str(payload.get("state") or "unknown"),
            gateway_ready=True,
            ingestion_ready=True,
            owner_number=self._optional_string(payload.get("owner_number")),
            qr_code=self._optional_string(payload.get("qr_code")),
            qr_expires_in_sec=self._optional_int(payload.get("qr_expires_in_sec")),
            last_seen_at=payload.get("last_seen_at"),
            last_error=self._optional_string(payload.get("last_error")),
        )

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

