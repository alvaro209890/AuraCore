from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.schemas import ObserverStatusResponse


class EvolutionApiError(RuntimeError):
    """Raised when Evolution API returns an unexpected response."""


@dataclass(slots=True)
class InstanceSnapshot:
    instance_name: str
    status: str
    profile_name: str | None = None
    owner_number: str | None = None


class EvolutionApiService:
    webhook_events = ("MESSAGES_UPSERT", "CONNECTION_UPDATE")

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def connect_observer(self) -> ObserverStatusResponse:
        snapshot = await self.ensure_observer_ready()
        return await self.get_observer_status(snapshot=snapshot, refresh_qr=True)

    async def get_observer_status(
        self,
        *,
        snapshot: InstanceSnapshot | None = None,
        refresh_qr: bool = False,
    ) -> ObserverStatusResponse:
        snapshot = snapshot or await self.fetch_instance()
        if snapshot is None:
            if not refresh_qr:
                return ObserverStatusResponse(
                    instance_name=self.settings.evolution_instance_name,
                    connected=False,
                    state="not_created",
                    webhook_ready=False,
                    last_seen_at=datetime.now(UTC),
                )
            snapshot = await self.ensure_observer_ready()
        else:
            await self.ensure_webhook()

        connection_payload = await self.get_connection_state()
        state = self._extract_connection_state(connection_payload) or snapshot.status or "unknown"
        connected = state.lower() == "open"
        qr_code: str | None = None
        pairing_code: str | None = None

        if refresh_qr and not connected:
            connect_payload = await self.connect_instance()
            qr_code = self._extract_qr_code(connect_payload)
            pairing_code = self._extract_pairing_code(connect_payload)

        return ObserverStatusResponse(
            instance_name=snapshot.instance_name,
            connected=connected,
            state=state,
            webhook_ready=True,
            profile_name=snapshot.profile_name,
            owner_number=snapshot.owner_number,
            qr_code=qr_code,
            pairing_code=pairing_code,
            last_seen_at=datetime.now(UTC),
        )

    async def ensure_observer_ready(self) -> InstanceSnapshot:
        snapshot = await self.fetch_instance()
        if snapshot is None:
            await self.create_instance()
            snapshot = await self.fetch_instance()

        if snapshot is None:
            raise EvolutionApiError("Observer instance could not be created or fetched.")

        await self.ensure_webhook()
        return snapshot

    async def fetch_instance(self) -> InstanceSnapshot | None:
        payload = await self._request(
            "GET",
            "/instance/fetchInstances",
            params={"instanceName": self.settings.evolution_instance_name},
        )
        candidates = self._extract_instances(payload)
        for candidate in candidates:
            instance = candidate.get("instance", candidate)
            if instance.get("instanceName") == self.settings.evolution_instance_name:
                return InstanceSnapshot(
                    instance_name=instance["instanceName"],
                    status=str(instance.get("status", "unknown")),
                    profile_name=instance.get("profileName"),
                    owner_number=self._normalize_owner(instance.get("owner")),
                )
        return None

    async def create_instance(self) -> Any:
        payload = {
            "instanceName": self.settings.evolution_instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "groupsIgnore": True,
            "alwaysOnline": False,
            "readMessages": False,
            "readStatus": False,
            "syncFullHistory": False,
            "webhook": {
                "url": self.settings.observer_webhook_url,
                "byEvents": True,
                "base64": False,
                "events": list(self.webhook_events),
            },
        }
        return await self._request("POST", "/instance/create", json=payload)

    async def ensure_settings(self) -> Any:
        payload = {
            "rejectCall": True,
            "msgCall": "AuraCore nao aceita chamadas.",
            "groupsIgnore": True,
            "alwaysOnline": False,
            "readMessages": False,
            "readStatus": False,
            "syncFullHistory": False,
        }
        return await self._request(
            "POST",
            f"/settings/set/{self.settings.evolution_instance_name}",
            json=payload,
        )

    async def ensure_webhook(self) -> Any:
        current = await self.find_webhook()
        current_events = set(current.get("events", [])) if current else set()
        webhook_enabled = bool(current.get("enabled")) if current else False
        current_url = current.get("url") if current else None
        if (
            not webhook_enabled
            or current_url != self.settings.observer_webhook_url
            or current_events != set(self.webhook_events)
        ):
            payload = {
                "enabled": True,
                "url": self.settings.observer_webhook_url,
                "webhook_by_events": True,
                "webhook_base64": False,
                "events": list(self.webhook_events),
            }
            return await self._request(
                "POST",
                f"/webhook/set/{self.settings.evolution_instance_name}",
                json=payload,
            )
        return current

    async def find_webhook(self) -> dict[str, Any] | None:
        try:
            payload = await self._request(
                "GET",
                f"/webhook/find/{self.settings.evolution_instance_name}",
            )
        except EvolutionApiError:
            return None

        if isinstance(payload, dict):
            return payload
        return None

    async def get_connection_state(self) -> Any:
        return await self._request(
            "GET",
            f"/instance/connectionState/{self.settings.evolution_instance_name}",
        )

    async def connect_instance(self) -> Any:
        return await self._request(
            "GET",
            f"/instance/connect/{self.settings.evolution_instance_name}",
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"apikey": self.settings.evolution_api_key}
        timeout = self.settings.request_timeout_seconds
        async with httpx.AsyncClient(
            base_url=self.settings.normalized_evolution_api_url,
            timeout=timeout,
            headers=headers,
        ) as client:
            response = await client.request(method, path, **kwargs)

        if response.status_code == 404:
            raise EvolutionApiError(f"Evolution endpoint not found: {path}")

        if response.status_code >= 400:
            detail = response.text.strip()
            raise EvolutionApiError(
                f"Evolution API request failed ({response.status_code}) on {path}: {detail}"
            )

        if not response.content:
            return None

        return response.json()

    def _extract_instances(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            instance = payload.get("instance")
            if isinstance(instance, dict):
                return [payload]
            response = payload.get("response")
            if isinstance(response, list):
                return [item for item in response if isinstance(item, dict)]
            if isinstance(response, dict):
                return [response]
        return []

    def _extract_connection_state(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None

        instance = payload.get("instance")
        if isinstance(instance, dict):
            state = instance.get("state")
            if state:
                return str(state)

        state = payload.get("state")
        if state:
            return str(state)
        return None

    def _extract_qr_code(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            code = payload.get("code")
            if code:
                return str(code)
        return None

    def _extract_pairing_code(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            pairing_code = payload.get("pairingCode")
            if pairing_code:
                return str(pairing_code)
        return None

    def _normalize_owner(self, owner: Any) -> str | None:
        if not owner:
            return None
        if isinstance(owner, dict):
            for key in ("jid", "number", "id"):
                value = owner.get(key)
                if value:
                    return str(value).split("@", maxsplit=1)[0]
        owner_value = str(owner)
        return owner_value.split("@", maxsplit=1)[0]
