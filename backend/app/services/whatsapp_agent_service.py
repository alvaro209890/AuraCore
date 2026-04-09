from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Sequence

from app.config import Settings
from app.schemas import (
    ObserverStatusResponse,
    WhatsAppAgentInboundMessageRequest,
    WhatsAppAgentInboundMessageResponse,
    WhatsAppAgentSettingsResponse,
    WhatsAppAgentStatusResponse,
)
from app.services.assistant_reply_service import AssistantReplyService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.supabase_store import (
    SupabaseStore,
    WhatsAppAgentSettingsRecord,
    WhatsAppAgentMessageRecord,
    WhatsAppAgentThreadRecord,
)


@dataclass(slots=True)
class AgentWorkspaceSnapshot:
    status: WhatsAppAgentStatusResponse
    settings: WhatsAppAgentSettingsResponse
    observer_status: ObserverStatusResponse
    threads: list[WhatsAppAgentThreadRecord]
    messages: list[WhatsAppAgentMessageRecord]
    active_thread_id: str | None


class WhatsAppAgentService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        reply_service: AssistantReplyService,
        observer_gateway: ObserverGatewayService,
        agent_gateway: WhatsAppAgentGatewayService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.reply_service = reply_service
        self.observer_gateway = observer_gateway
        self.agent_gateway = agent_gateway

    async def get_status(self) -> WhatsAppAgentStatusResponse:
        agent_status = await self.agent_gateway.get_agent_status()
        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            settings_record = self._sync_settings_with_observer(observer_status)
        except Exception:
            settings_record = self.store.get_whatsapp_agent_settings(self.settings.default_user_id)
        return self._build_status_response(agent_status=agent_status, settings=settings_record)

    async def connect_agent(self) -> WhatsAppAgentStatusResponse:
        agent_status = await self.agent_gateway.connect_agent()
        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            settings_record = self._sync_settings_with_observer(observer_status)
        except Exception:
            settings_record = self.store.get_whatsapp_agent_settings(self.settings.default_user_id)
        return self._build_status_response(agent_status=agent_status, settings=settings_record)

    async def reset_agent(self) -> WhatsAppAgentStatusResponse:
        agent_status = await self.agent_gateway.reset_agent()
        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            settings_record = self._sync_settings_with_observer(observer_status)
        except Exception:
            settings_record = self.store.get_whatsapp_agent_settings(self.settings.default_user_id)
        return self._build_status_response(agent_status=agent_status, settings=settings_record)

    async def build_workspace(self, *, thread_id: str | None = None) -> AgentWorkspaceSnapshot:
        agent_status = await self.agent_gateway.get_agent_status()
        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            settings_record = self._sync_settings_with_observer(observer_status)
        except Exception:
            observer_status = ObserverStatusResponse(
                instance_name="observer",
                connected=False,
                state="unknown",
                gateway_ready=False,
                ingestion_ready=False,
            )
            settings_record = self.store.get_whatsapp_agent_settings(self.settings.default_user_id)
        threads = self.store.list_whatsapp_agent_threads(user_id=self.settings.default_user_id, limit=24)
        active_thread_id = self._resolve_active_thread_id(threads, thread_id)
        messages = (
            self.store.list_whatsapp_agent_messages(thread_id=active_thread_id, limit=max(1, self.settings.chat_max_history_messages))
            if active_thread_id
            else []
        )
        status_response = self._build_status_response(agent_status=agent_status, settings=settings_record)
        settings_response = self._build_settings_response(settings_record)
        return AgentWorkspaceSnapshot(
            status=status_response,
            settings=settings_response,
            observer_status=observer_status,
            threads=threads,
            messages=messages,
            active_thread_id=active_thread_id,
        )

    def update_settings(self, *, auto_reply_enabled: bool | None) -> WhatsAppAgentSettingsResponse:
        updated = self.store.update_whatsapp_agent_settings(
            user_id=self.settings.default_user_id,
            auto_reply_enabled=auto_reply_enabled,
            updated_at=datetime.now(UTC),
        )
        return self._build_settings_response(updated)

    def list_threads(self, *, limit: int = 24) -> list[WhatsAppAgentThreadRecord]:
        return self.store.list_whatsapp_agent_threads(
            user_id=self.settings.default_user_id,
            limit=limit,
        )

    def list_messages(self, *, thread_id: str, limit: int = 40) -> list[WhatsAppAgentMessageRecord]:
        return self.store.list_whatsapp_agent_messages(thread_id=thread_id, limit=limit)

    async def handle_inbound_message(
        self,
        payload: WhatsAppAgentInboundMessageRequest,
    ) -> WhatsAppAgentInboundMessageResponse:
        normalized_text = " ".join(payload.message_text.split()).strip()
        chat_jid = payload.chat_jid.strip()
        contact_phone = self.store.normalize_contact_phone(payload.contact_phone)
        contact_name = (payload.contact_name or payload.contact_phone or "Contato").strip()

        if not normalized_text:
            return WhatsAppAgentInboundMessageResponse(action="ignored_empty")
        if not chat_jid or not self.store.is_direct_chat_jid(chat_jid):
            return WhatsAppAgentInboundMessageResponse(action="ignored_non_direct")
        if not contact_phone:
            return WhatsAppAgentInboundMessageResponse(action="ignored_invalid_contact")
        if payload.from_me or payload.direction == "outbound":
            return WhatsAppAgentInboundMessageResponse(action="ignored_from_me")

        if self.store.get_whatsapp_agent_message_by_whatsapp_id(
            user_id=self.settings.default_user_id,
            whatsapp_message_id=payload.message_id,
        ):
            return WhatsAppAgentInboundMessageResponse(action="duplicate_message")

        try:
            agent_status = await self.agent_gateway.get_agent_status()
            agent_owner_number = self.store.normalize_contact_phone(agent_status.owner_number)
            if agent_owner_number and contact_phone == agent_owner_number:
                return WhatsAppAgentInboundMessageResponse(action="ignored_self")
        except Exception:
            agent_owner_number = None

        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            settings_record = self._sync_settings_with_observer(observer_status)
        except Exception:
            observer_status = ObserverStatusResponse(
                instance_name="observer",
                connected=False,
                state="unknown",
                gateway_ready=False,
                ingestion_ready=False,
            )
            settings_record = self.store.get_whatsapp_agent_settings(self.settings.default_user_id)
        allowed_contact_phone = settings_record.allowed_contact_phone

        thread = self.store.get_or_create_whatsapp_agent_thread(
            user_id=self.settings.default_user_id,
            contact_phone=contact_phone,
            chat_jid=chat_jid,
            contact_name=contact_name,
            created_at=payload.timestamp,
        )

        inbound_message = self.store.append_whatsapp_agent_message(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            direction="inbound",
            role="user",
            content=normalized_text,
            message_timestamp=payload.timestamp,
            contact_phone=contact_phone,
            chat_jid=chat_jid,
            whatsapp_message_id=payload.message_id,
            processing_status="received",
            metadata={
                "source": payload.source,
                "from_me": bool(payload.from_me),
            },
            created_at=datetime.now(UTC),
        )

        self.store.update_whatsapp_agent_thread(
            thread_id=thread.id,
            last_message_at=payload.timestamp,
            last_inbound_at=payload.timestamp,
        )

        if not allowed_contact_phone:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="ignored_missing_allowlist",
            )
            return WhatsAppAgentInboundMessageResponse(
                action="ignored_missing_allowlist",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        if allowed_contact_phone and contact_phone != allowed_contact_phone:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="ignored_not_allowed",
            )
            self.store.update_whatsapp_agent_thread(
                thread_id=thread.id,
                status="blocked",
                last_error_at=datetime.now(UTC),
                last_error_text="Contato nao autorizado para o WhatsApp agente.",
            )
            return WhatsAppAgentInboundMessageResponse(
                action="ignored_not_allowed",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        if self.store.get_whatsapp_agent_outbound_for_source_inbound(
            user_id=self.settings.default_user_id,
            source_inbound_message_id=payload.message_id,
        ):
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="duplicate_reply",
            )
            return WhatsAppAgentInboundMessageResponse(
                action="duplicate_reply",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        if not settings_record.auto_reply_enabled:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="auto_reply_disabled",
            )
            return WhatsAppAgentInboundMessageResponse(
                action="auto_reply_disabled",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        prior_messages = self.store.list_whatsapp_agent_messages(
            thread_id=thread.id,
            limit=max(1, self.settings.chat_max_history_messages),
        )
        prior_messages = [msg for msg in prior_messages if msg.id != inbound_message.id]

        started_at = perf_counter()
        error_text: str | None = None
        assistant_reply: str | None = None
        model_run_id: str | None = None
        try:
            assistant_reply = await self.reply_service.generate_reply(
                user_message=normalized_text,
                recent_messages=prior_messages,
                context_hint=None,
            )
        except Exception as error:
            error_text = str(error)

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        model_run = self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=None,
            provider="groq",
            model_name=self.settings.groq_model,
            run_type="whatsapp_agent_reply",
            success=assistant_reply is not None,
            latency_ms=elapsed_ms,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=error_text,
            created_at=datetime.now(UTC),
        )
        model_run_id = model_run.id if model_run else None
        if assistant_reply is None:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="failed_reply",
                error_text=error_text,
            )
            self.store.update_whatsapp_agent_thread(
                thread_id=thread.id,
                last_error_at=datetime.now(UTC),
                last_error_text=error_text,
            )
            return WhatsAppAgentInboundMessageResponse(
                action="failed_reply",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        outbound_message = self.store.append_whatsapp_agent_message(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            direction="outbound",
            role="assistant",
            content=assistant_reply,
            message_timestamp=datetime.now(UTC),
            contact_phone=contact_phone,
            chat_jid=chat_jid,
            source_inbound_message_id=payload.message_id,
            processing_status="sending",
            response_latency_ms=elapsed_ms,
            model_run_id=model_run_id,
            metadata={"generated_by": "groq"},
            created_at=datetime.now(UTC),
        )

        send_error: str | None = None
        send_status = "sent"
        try:
            send_result = await self.agent_gateway.send_text_message(
                chat_jid=chat_jid,
                message_text=assistant_reply,
            )
            self.store.update_whatsapp_agent_message(
                message_id=outbound_message.id,
                send_status="sent",
                processing_status="sent",
                whatsapp_message_id=send_result.message_id,
                response_latency_ms=elapsed_ms,
                message_timestamp=send_result.timestamp or datetime.now(UTC),
            )
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="replied",
            )
            self.store.update_whatsapp_agent_thread(
                thread_id=thread.id,
                status="active",
                last_outbound_at=datetime.now(UTC),
                last_message_at=datetime.now(UTC),
                last_error_at=None,
                last_error_text=None,
            )
        except Exception as error:
            send_status = "failed"
            send_error = str(error)
            self.store.update_whatsapp_agent_message(
                message_id=outbound_message.id,
                send_status="failed",
                processing_status="failed_send",
                error_text=send_error,
            )
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="reply_failed_send",
                error_text=send_error,
            )
            self.store.update_whatsapp_agent_thread(
                thread_id=thread.id,
                status="error",
                last_error_at=datetime.now(UTC),
                last_error_text=send_error,
            )

        return WhatsAppAgentInboundMessageResponse(
            action="replied" if send_status == "sent" else "failed_send",
            thread_id=thread.id,
            inbound_message_id=inbound_message.id,
            outbound_message_id=outbound_message.id,
        )

    def _sync_settings_with_observer(self, observer_status: ObserverStatusResponse) -> WhatsAppAgentSettingsRecord:
        current = self.store.get_whatsapp_agent_settings(self.settings.default_user_id)
        observer_owner = self.store.normalize_contact_phone(observer_status.owner_number)
        if observer_owner and observer_owner != current.allowed_contact_phone:
            return self.store.update_whatsapp_agent_settings(
                user_id=self.settings.default_user_id,
                allowed_contact_phone=observer_owner,
                updated_at=datetime.now(UTC),
            )
        return current

    def _build_status_response(
        self,
        *,
        agent_status: ObserverStatusResponse,
        settings: WhatsAppAgentSettingsRecord,
    ) -> WhatsAppAgentStatusResponse:
        settings_record = settings
        return WhatsAppAgentStatusResponse(
            instance_name=agent_status.instance_name,
            connected=agent_status.connected,
            state=agent_status.state,
            gateway_ready=agent_status.gateway_ready,
            auto_reply_enabled=settings_record.auto_reply_enabled,
            owner_number=agent_status.owner_number,
            allowed_contact_phone=settings_record.allowed_contact_phone,
            qr_code=agent_status.qr_code,
            qr_expires_in_sec=agent_status.qr_expires_in_sec,
            last_seen_at=agent_status.last_seen_at,
            last_error=agent_status.last_error,
        )

    def _build_settings_response(self, settings_record: WhatsAppAgentSettingsRecord) -> WhatsAppAgentSettingsResponse:
        return WhatsAppAgentSettingsResponse(
            user_id=str(settings_record.user_id),
            auto_reply_enabled=settings_record.auto_reply_enabled,
            allowed_contact_phone=settings_record.allowed_contact_phone,
            updated_at=settings_record.updated_at,
        )

    def _resolve_active_thread_id(
        self,
        threads: Sequence[WhatsAppAgentThreadRecord],
        thread_id: str | None,
    ) -> str | None:
        if thread_id and any(thread.id == thread_id for thread in threads):
            return thread_id
        if threads:
            return threads[0].id
        return None
