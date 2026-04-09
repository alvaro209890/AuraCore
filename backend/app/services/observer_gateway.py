from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings
from app.schemas import ObserverStatusResponse


class ObserverGatewayError(RuntimeError):
    """Raised when the WhatsApp gateway is unavailable or returns invalid data."""


@dataclass(slots=True)
class WhatsAppGatewaySendResult:
    message_id: str | None
    timestamp: datetime | None


class _BaseWhatsAppGatewayService:
    def __init__(self, *, settings: Settings, channel_name: str) -> None:
        self.settings = settings
        self.channel_name = channel_name

    async def connect(self) -> ObserverStatusResponse:
        payload = await self._request("POST", f"/internal/{self.channel_name}/connect")
        return self._build_status(payload)

    async def reset(self) -> ObserverStatusResponse:
        payload = await self._request("POST", f"/internal/{self.channel_name}/reset")
        return self._build_status(payload)

    async def get_status(self) -> ObserverStatusResponse:
        payload = await self._request("GET", f"/internal/{self.channel_name}/status")
        return self._build_status(payload)

    async def send_text_message(self, *, chat_jid: str, message_text: str) -> WhatsAppGatewaySendResult:
        payload = await self._request(
            "POST",
            f"/internal/{self.channel_name}/send",
            json={"chat_jid": chat_jid, "message_text": message_text},
        )
        return WhatsAppGatewaySendResult(
            message_id=self._optional_string(payload.get("message_id")),
            timestamp=self._parse_datetime(payload.get("timestamp")),
        )

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"x-internal-api-token": self.settings.internal_api_token}
        timeout = self.settings.request_timeout_seconds

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_whatsapp_gateway_url,
            timeout=timeout,
            headers=headers,
        ) as client:
            response = await client.request(method, path, json=json)

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
            instance_name=str(payload.get("instance_name") or self.channel_name),
            connected=bool(payload.get("connected")),
            state=str(payload.get("state") or "unknown"),
            gateway_ready=True,
            ingestion_ready=True,
            owner_number=self._optional_string(payload.get("owner_number")),
            qr_code=self._optional_string(payload.get("qr_code")),
            qr_expires_in_sec=self._optional_int(payload.get("qr_expires_in_sec")),
            last_seen_at=self._parse_datetime(payload.get("last_seen_at")),
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

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None


class ObserverGatewayService(_BaseWhatsAppGatewayService):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings=settings, channel_name="observer")

    async def connect_observer(self) -> ObserverStatusResponse:
        return await self.connect()

    async def reset_observer(self) -> ObserverStatusResponse:
        return await self.reset()

    async def refresh_observer_messages(self) -> ObserverStatusResponse:
        payload = await self._request("POST", "/internal/observer/messages/refresh")
        return self._build_status(payload)

    async def get_observer_status(self, *, refresh_qr: bool = False) -> ObserverStatusResponse:
        if refresh_qr:
            return await self.connect_observer()
        return await self.get_status()


class WhatsAppAgentGatewayService(_BaseWhatsAppGatewayService):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings=settings, channel_name="agent")

    async def connect_agent(self) -> ObserverStatusResponse:
        return await self.connect()

    async def reset_agent(self) -> ObserverStatusResponse:
        return await self.reset()

    async def get_agent_status(self) -> ObserverStatusResponse:
        return await self.get_status()
