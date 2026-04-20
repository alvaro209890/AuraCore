from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from time import perf_counter
from typing import Mapping, Sequence

from app.config import Settings
from app.schemas import (
    ObserverStatusResponse,
    WhatsAppAgentInboundMessageRequest,
    WhatsAppAgentInboundMessageResponse,
    WhatsAppAgentSettingsResponse,
    WhatsAppAgentStatusResponse,
)
from app.services.agenda_guardian_service import AgendaGuardianService, AgendaProcessingResult
from app.services.assistant_reply_service import AssistantReplyService
from app.services.deepseek_service import DeepSeekAgentMemoryDecision, DeepSeekService
from app.services.groq_service import GroqChatService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.proactive_assistant_service import ProactiveAssistantService
from app.services.supabase_store import (
    ImportantMessageSeed,
    SupabaseStore,
    WhatsAppAgentContactMemoryRecord,
    WhatsAppAgentMessageRecord,
    WhatsAppAgentSettingsRecord,
    WhatsAppAgentThreadRecord,
    WhatsAppAgentThreadSessionRecord,
)

logger = logging.getLogger("auracore.agent_reply")


@dataclass(slots=True)
class AgentLearningOutcome:
    status: str
    model_run_id: str | None
    learned_at: datetime | None
    memory: WhatsAppAgentContactMemoryRecord | None
    last_decision: DeepSeekAgentMemoryDecision | None = None
    error_text: str | None = None


@dataclass(slots=True)
class AgentWorkspaceSnapshot:
    status: WhatsAppAgentStatusResponse
    settings: WhatsAppAgentSettingsResponse
    observer_status: ObserverStatusResponse
    threads: list[WhatsAppAgentThreadRecord]
    messages: list[WhatsAppAgentMessageRecord]
    active_thread_id: str | None
    active_session: WhatsAppAgentThreadSessionRecord | None
    contact_memory: WhatsAppAgentContactMemoryRecord | None


@dataclass(slots=True)
class AgentOutboundMessage:
    text: str
    generated_by: str
    metadata: Mapping[str, object]


class WhatsAppAgentService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        reply_service: AssistantReplyService,
        deepseek_service: DeepSeekService,
        groq_service: GroqChatService,
        observer_gateway: ObserverGatewayService,
        agent_gateway: WhatsAppAgentGatewayService,
        agenda_guardian_service: AgendaGuardianService,
        proactive_assistant_service: ProactiveAssistantService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.reply_service = reply_service
        self.deepseek_service = deepseek_service
        self.groq_service = groq_service
        self.observer_gateway = observer_gateway
        self.agent_gateway = agent_gateway
        self.agenda_guardian_service = agenda_guardian_service
        self.proactive_assistant_service = proactive_assistant_service

    async def get_status(self) -> WhatsAppAgentStatusResponse:
        agent_status = await self.agent_gateway.get_agent_status()
        _, settings_record = await self._load_observer_context()
        return self._build_status_response(agent_status=agent_status, settings=settings_record)

    async def connect_agent(self) -> WhatsAppAgentStatusResponse:
        agent_status = await self.agent_gateway.connect_agent()
        _, settings_record = await self._load_observer_context()
        return self._build_status_response(agent_status=agent_status, settings=settings_record)

    async def reset_agent(self) -> WhatsAppAgentStatusResponse:
        agent_status = await self.agent_gateway.reset_agent()
        _, settings_record = await self._load_observer_context()
        return self._build_status_response(agent_status=agent_status, settings=settings_record)

    async def build_workspace(self, *, thread_id: str | None = None) -> AgentWorkspaceSnapshot:
        agent_status = await self.agent_gateway.get_agent_status()
        observer_status, settings_record = await self._load_observer_context()

        threads = self.store.list_whatsapp_agent_threads(user_id=self.settings.default_user_id, limit=24)
        active_thread_id = self._resolve_active_thread_id(threads, thread_id)
        active_thread = (
            self.store.get_whatsapp_agent_thread(user_id=self.settings.default_user_id, thread_id=active_thread_id)
            if active_thread_id
            else None
        )
        messages = (
            self.store.list_whatsapp_agent_messages(
                thread_id=active_thread_id,
                limit=max(1, self.settings.context_max_history_messages * 4),
            )
            if active_thread_id
            else []
        )
        active_session = (
            self.store.get_whatsapp_agent_active_session(
                user_id=self.settings.default_user_id,
                thread_id=active_thread.id,
            )
            if active_thread is not None
            else None
        )
        contact_memory = (
            self.store.get_whatsapp_agent_contact_memory(
                user_id=self.settings.default_user_id,
                contact_phone=active_thread.contact_phone,
            )
            if active_thread is not None and active_thread.contact_phone
            else None
        )
        return AgentWorkspaceSnapshot(
            status=self._build_status_response(agent_status=agent_status, settings=settings_record),
            settings=self._build_settings_response(settings_record),
            observer_status=observer_status,
            threads=threads,
            messages=messages,
            active_thread_id=active_thread_id,
            active_session=active_session,
            contact_memory=contact_memory,
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

    def get_active_session_for_thread(self, *, thread_id: str) -> WhatsAppAgentThreadSessionRecord | None:
        return self.store.get_whatsapp_agent_active_session(
            user_id=self.settings.default_user_id,
            thread_id=thread_id,
        )

    def get_contact_memory_for_thread(self, thread: WhatsAppAgentThreadRecord) -> WhatsAppAgentContactMemoryRecord | None:
        if not thread.contact_phone:
            return None
        return self.store.get_whatsapp_agent_contact_memory(
            user_id=self.settings.default_user_id,
            contact_phone=thread.contact_phone,
        )

    async def handle_inbound_message(
        self,
        payload: WhatsAppAgentInboundMessageRequest,
    ) -> WhatsAppAgentInboundMessageResponse:
        raw_text = " ".join(payload.message_text.split()).strip()
        chat_jid = payload.chat_jid.strip()
        contact_phone = self.store.normalize_contact_phone(payload.contact_phone)
        contact_name = (payload.contact_name or payload.contact_phone or "Contato").strip()
        contact_name_source = (payload.contact_name_source or "unknown").strip() or "unknown"
        source_event = (payload.source_event or "unknown").strip() or "unknown"
        media_type = (payload.media_type or "text").strip().lower() or "text"
        transcript_text: str | None = None
        transcription_error: str | None = None

        if media_type == "audio" and payload.audio_data_url:
            try:
                transcript_text = " ".join(
                    (await self.groq_service.transcribe_audio_data_url(payload.audio_data_url)).split()
                ).strip()
            except Exception as error:
                transcription_error = str(error)
                logger.warning(
                    "agent_audio_transcription_failed message_id=%s contact_phone=%s detail=%s",
                    payload.message_id,
                    contact_phone,
                    transcription_error,
                )

        normalized_text = raw_text
        if transcript_text:
            if normalized_text and transcript_text.casefold() != normalized_text.casefold():
                normalized_text = f"{normalized_text}\n\n[Transcricao de audio] {transcript_text}".strip()
            else:
                normalized_text = f"[Audio transcrito] {transcript_text}"

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

        observer_status, settings_record = await self._load_observer_context()
        observer_owner_number = self._resolve_observer_owner_number(observer_status=observer_status)
        owner_self_message = (
            True
            if observer_owner_number is None
            else self.store.phone_matches(contact_phone, observer_owner_number)
        )
        if observer_owner_number and not owner_self_message:
            return WhatsAppAgentInboundMessageResponse(action="ignored_unknown_contact")

        thread = self.store.get_or_create_whatsapp_agent_thread(
            user_id=self.settings.default_user_id,
            contact_phone=contact_phone,
            chat_jid=chat_jid,
            contact_name=contact_name,
            created_at=payload.timestamp,
        )
        delivery_chat_jid = thread.chat_jid or chat_jid
        session, _started_new_session = self.store.resolve_whatsapp_agent_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=contact_phone,
            chat_jid=delivery_chat_jid,
            activity_at=payload.timestamp,
            idle_timeout_minutes=self.settings.whatsapp_agent_idle_timeout_minutes,
        )

        inbound_message = self.store.append_whatsapp_agent_message(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            direction="inbound",
            role="user",
            session_id=session.id,
            content=normalized_text,
            message_timestamp=payload.timestamp,
            contact_phone=contact_phone,
            chat_jid=chat_jid,
            whatsapp_message_id=payload.message_id,
            processing_status="received",
            learning_status="pending_review",
            metadata={
                "source": payload.source,
                "source_event": source_event,
                "from_me": bool(payload.from_me),
                "observer_owner_number": observer_status.owner_number,
                "contact_name_source": contact_name_source,
                "media_type": media_type,
                "audio_transcribed": bool(transcript_text),
                "audio_transcription_error": transcription_error,
                "owner_self_message": owner_self_message,
            },
            created_at=datetime.now(UTC),
        )

        self.store.update_whatsapp_agent_thread(
            thread_id=thread.id,
            status="active",
            last_message_at=payload.timestamp,
            last_inbound_at=payload.timestamp,
            last_error_at=None,
            last_error_text=None,
        )

        if self.store.get_whatsapp_agent_outbound_for_source_inbound(
            user_id=self.settings.default_user_id,
            source_inbound_message_id=payload.message_id,
        ):
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="duplicate_reply",
                learning_status="not_applicable",
            )
            return WhatsAppAgentInboundMessageResponse(
                action="duplicate_reply",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        contact_memory = self.store.get_whatsapp_agent_contact_memory(
            user_id=self.settings.default_user_id,
            contact_phone=contact_phone,
        )
        learning_outcome = await self._learn_from_inbound_message(
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            contact_memory=contact_memory,
        )
        if learning_outcome.memory is not None:
            contact_memory = learning_outcome.memory

        reply_started = perf_counter()
        conflict_resolution_outcome = None
        if owner_self_message:
            conflict_resolution_outcome = await self.agenda_guardian_service.resolve_conflict_reply(
                user_id=self.settings.default_user_id,
                contact_phone=contact_phone,
                message_id=payload.message_id,
                message_text=normalized_text,
                occurred_at=payload.timestamp,
            )

        if conflict_resolution_outcome is not None and conflict_resolution_outcome.handled:
            if not settings_record.auto_reply_enabled:
                self.store.update_whatsapp_agent_message(
                    message_id=inbound_message.id,
                    processing_status=(
                        "agenda_conflict_resolved_no_reply"
                        if conflict_resolution_outcome.applied
                        else "agenda_conflict_needs_clarification_no_reply"
                    ),
                )
                return WhatsAppAgentInboundMessageResponse(
                    action=(
                        "agenda_conflict_resolved_no_reply"
                        if conflict_resolution_outcome.applied
                        else "agenda_conflict_needs_clarification_no_reply"
                    ),
                    thread_id=thread.id,
                    inbound_message_id=inbound_message.id,
                )

            assistant_reply = conflict_resolution_outcome.assistant_reply or (
                "Entendi a resposta, mas ainda preciso de uma confirmação mais clara para aplicar a mudança."
            )
            return await self._send_outbound_reply(
                payload=payload,
                inbound_message=inbound_message,
                thread=thread,
                session=session,
                contact_phone=contact_phone,
                delivery_chat_jid=delivery_chat_jid,
                assistant_reply=assistant_reply,
                response_latency_ms=int((perf_counter() - reply_started) * 1000),
                reply_model_run_id=None,
                generated_by="agenda_conflict_resolver",
            )

        agenda_outcome = await self.agenda_guardian_service.process_agent_message(
            user_id=self.settings.default_user_id,
            message_id=payload.message_id,
            contact_name=contact_name,
            message_text=normalized_text,
            occurred_at=payload.timestamp,
        )

        proactive_reply_outcome = None
        if owner_self_message:
            learning_decision = learning_outcome.last_decision
            await self.proactive_assistant_service.capture_owner_message(
                thread_id=thread.id,
                contact_phone=contact_phone,
                chat_jid=delivery_chat_jid,
                source_message_id=payload.message_id,
                message_text=normalized_text,
                occurred_at=payload.timestamp,
                learning_signals=(
                    {
                        "mood_signals": learning_decision.mood_signals,
                        "implied_urgency": learning_decision.implied_urgency,
                        "implied_tasks": learning_decision.implied_tasks,
                    }
                    if learning_decision is not None
                    else {}
                ),
            )
            proactive_reply_outcome = self.proactive_assistant_service.handle_owner_reply(
                contact_phone=contact_phone,
                message_text=normalized_text,
                occurred_at=payload.timestamp,
            )

        if not settings_record.auto_reply_enabled:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status=(
                    "scheduled_no_reply"
                    if agenda_outcome.detected
                    else "proactive_handled_no_reply"
                    if proactive_reply_outcome is not None and proactive_reply_outcome.handled
                    else "auto_reply_disabled"
                ),
            )
            return WhatsAppAgentInboundMessageResponse(
                action=(
                    "scheduled_no_reply"
                    if agenda_outcome.detected
                    else "proactive_handled_no_reply"
                    if proactive_reply_outcome is not None and proactive_reply_outcome.handled
                    else "auto_reply_disabled"
                ),
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        if proactive_reply_outcome is not None and proactive_reply_outcome.handled and proactive_reply_outcome.assistant_reply:
            return await self._send_outbound_reply(
                payload=payload,
                inbound_message=inbound_message,
                thread=thread,
                session=session,
                contact_phone=contact_phone,
                delivery_chat_jid=delivery_chat_jid,
                assistant_reply=proactive_reply_outcome.assistant_reply,
                response_latency_ms=int((perf_counter() - reply_started) * 1000),
                reply_model_run_id=None,
                generated_by="proactive_assistant_reply",
            )

        reply_started = perf_counter()
        prior_messages = self.store.list_whatsapp_agent_session_messages(
            session_id=session.id,
            limit=max(1, self.settings.context_max_history_messages),
        )
        prior_messages = [message for message in prior_messages if message.id != inbound_message.id]

        assistant_reply: str | None = None
        reply_error_text: str | None = None
        reply_model_run_id: str | None = None
        reply_generated_by = "agenda_guardian" if agenda_outcome.detected else "groq"

        contact_memory_context = self._build_rich_contact_context(
            memory=contact_memory,
            learning_outcome=learning_outcome,
        )

        if agenda_outcome.detected:
            assistant_reply = self._build_agenda_confirmation_reply(agenda_outcome)
        else:
            try:
                assistant_reply = await self.reply_service.generate_reply(
                    user_message=normalized_text,
                    recent_messages=prior_messages,
                    context_hint=None,
                    priority_context=None,
                    contact_memory_context=contact_memory_context,
                    channel="whatsapp_agent",
                )
            except Exception as error:
                reply_error_text = str(error)

        reply_elapsed_ms = int((perf_counter() - reply_started) * 1000)

        if not agenda_outcome.detected:
            reply_model_run = self.store.create_model_run(
                user_id=self.settings.default_user_id,
                job_id=None,
                provider="groq",
                model_name=self.settings.whatsapp_agent_groq_model,
                run_type="whatsapp_agent_reply",
                success=assistant_reply is not None,
                latency_ms=reply_elapsed_ms,
                input_tokens=None,
                output_tokens=None,
                reasoning_tokens=None,
                estimated_cost_usd=None,
                error_text=reply_error_text,
                created_at=datetime.now(UTC),
            )
            reply_model_run_id = reply_model_run.id if reply_model_run else None

        if assistant_reply is None:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                processing_status="failed_reply",
                error_text=reply_error_text,
            )
            self.store.update_whatsapp_agent_thread(
                thread_id=thread.id,
                status="error",
                last_error_at=datetime.now(UTC),
                last_error_text=reply_error_text,
            )
            return WhatsAppAgentInboundMessageResponse(
                action="failed_reply",
                thread_id=thread.id,
                inbound_message_id=inbound_message.id,
            )

        return await self._send_outbound_reply(
            payload=payload,
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            contact_phone=contact_phone,
            delivery_chat_jid=delivery_chat_jid,
            assistant_reply=assistant_reply,
            response_latency_ms=reply_elapsed_ms,
            reply_model_run_id=reply_model_run_id,
            generated_by=reply_generated_by,
        )

    async def _load_observer_context(self) -> tuple[ObserverStatusResponse, WhatsAppAgentSettingsRecord]:
        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            settings_record = self._sync_settings_with_observer(observer_status)
            return observer_status, settings_record
        except Exception:
            observer_status = ObserverStatusResponse(
                instance_name="observer",
                connected=False,
                state="unknown",
                gateway_ready=False,
                ingestion_ready=False,
                owner_number=None,
                qr_code=None,
                qr_expires_in_sec=None,
                last_seen_at=None,
                last_error="observer_unavailable",
            )
            return observer_status, self.store.get_whatsapp_agent_settings(self.settings.default_user_id)

    def _resolve_observer_owner_number(self, *, observer_status: ObserverStatusResponse) -> str | None:
        direct_owner = self.store.normalize_contact_phone(observer_status.owner_number)
        if direct_owner:
            return direct_owner
        return self.store.get_whatsapp_session_owner_phone(
            session_id=f"{self.settings.default_user_id}:observer"
        )

    async def _send_outbound_reply(
        self,
        *,
        payload: WhatsAppAgentInboundMessageRequest,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        contact_phone: str,
        delivery_chat_jid: str,
        assistant_reply: str,
        response_latency_ms: int,
        reply_model_run_id: str | None,
        generated_by: str,
    ) -> WhatsAppAgentInboundMessageResponse:
        return await self._send_outbound_messages(
            payload=payload,
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            contact_phone=contact_phone,
            delivery_chat_jid=delivery_chat_jid,
            outbound_messages=[
                AgentOutboundMessage(
                    text=assistant_reply,
                    generated_by=generated_by,
                    metadata={
                        "reply_to_message_id": inbound_message.whatsapp_message_id,
                        "delivery_chat_jid": delivery_chat_jid,
                        "model_run_id": reply_model_run_id,
                    },
                )
            ],
            response_latency_ms=response_latency_ms,
        )

    async def _send_outbound_messages(
        self,
        *,
        payload: WhatsAppAgentInboundMessageRequest,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        contact_phone: str,
        delivery_chat_jid: str,
        outbound_messages: Sequence[AgentOutboundMessage],
        response_latency_ms: int,
    ) -> WhatsAppAgentInboundMessageResponse:
        stored_messages: list[WhatsAppAgentMessageRecord] = []
        message_ids: list[str] = []
        last_sent_at: datetime | None = None

        for index, outbound in enumerate(outbound_messages):
            source_inbound_message_id = (
                payload.message_id
                if index == 0 and self._can_claim_source_inbound_message(payload.message_id)
                else None
            )
            outbound_record = self.store.append_whatsapp_agent_message(
                user_id=self.settings.default_user_id,
                thread_id=thread.id,
                direction="outbound",
                role="assistant",
                session_id=session.id,
                content=outbound.text,
                message_timestamp=datetime.now(UTC),
                contact_phone=contact_phone,
                chat_jid=delivery_chat_jid,
                source_inbound_message_id=source_inbound_message_id,
                processing_status="sending",
                learning_status="not_applicable",
                response_latency_ms=response_latency_ms if index == 0 else None,
                model_run_id=(
                    str(outbound.metadata.get("model_run_id"))
                    if isinstance(outbound.metadata.get("model_run_id"), str)
                    else None
                ),
                metadata={
                    "generated_by": outbound.generated_by,
                    "reply_to_message_id": inbound_message.whatsapp_message_id,
                    "delivery_chat_jid": delivery_chat_jid,
                    **outbound.metadata,
                },
                created_at=datetime.now(UTC),
            )
            stored_messages.append(outbound_record)

            try:
                send_result = await self.agent_gateway.send_text_message(
                    chat_jid=delivery_chat_jid,
                    message_text=outbound.text,
                )
            except Exception as error:
                send_error = str(error)
                self.store.update_whatsapp_agent_message(
                    message_id=outbound_record.id,
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
                logger.error(
                    "reply_send_failed thread_id=%s inbound_message_id=%s outbound_message_id=%s contact_phone=%s chat_jid=%s error=%s",
                    thread.id,
                    inbound_message.id,
                    outbound_record.id,
                    contact_phone,
                    delivery_chat_jid,
                    send_error,
                )
                return WhatsAppAgentInboundMessageResponse(
                    action="failed_send",
                    thread_id=thread.id,
                    inbound_message_id=inbound_message.id,
                    outbound_message_id=stored_messages[0].id if stored_messages else outbound_record.id,
                    outbound_message_ids=[message.id for message in stored_messages],
                    outbound_count=len(stored_messages),
                )

            sent_at = send_result.timestamp or datetime.now(UTC)
            last_sent_at = sent_at
            self.store.update_whatsapp_agent_message(
                message_id=outbound_record.id,
                send_status="sent",
                processing_status="sent",
                whatsapp_message_id=send_result.message_id,
                response_latency_ms=response_latency_ms if index == 0 else None,
                message_timestamp=sent_at,
            )
            message_ids.append(outbound_record.id)

        resolved_status = "replied" if message_ids else "no_reply"
        self.store.update_whatsapp_agent_message(
            message_id=inbound_message.id,
            processing_status=resolved_status,
            error_text=None,
        )
        if last_sent_at is not None:
            self.store.update_whatsapp_agent_thread(
                thread_id=thread.id,
                chat_jid=delivery_chat_jid,
                status="active",
                last_outbound_at=last_sent_at,
                last_message_at=last_sent_at,
                last_error_at=None,
                last_error_text=None,
            )
            self.store.update_whatsapp_agent_session(
                session_id=session.id,
                last_activity_at=last_sent_at,
                updated_at=last_sent_at,
            )

        logger.info(
            "reply_sent thread_id=%s inbound_message_id=%s outbound_count=%s contact_phone=%s chat_jid=%s latency_ms=%s",
            thread.id,
            inbound_message.id,
            len(message_ids),
            contact_phone,
            delivery_chat_jid,
            response_latency_ms,
        )
        return WhatsAppAgentInboundMessageResponse(
            action="replied",
            thread_id=thread.id,
            inbound_message_id=inbound_message.id,
            outbound_message_id=message_ids[0] if message_ids else None,
            outbound_message_ids=message_ids,
            outbound_count=len(message_ids),
        )

    def _can_claim_source_inbound_message(self, source_inbound_message_id: str | None) -> bool:
        normalized_id = str(source_inbound_message_id or "").strip()
        if not normalized_id:
            return False
        existing = self.store.get_whatsapp_agent_outbound_for_source_inbound(
            user_id=self.settings.default_user_id,
            source_inbound_message_id=normalized_id,
        )
        return existing is None

    def _build_agenda_confirmation_reply(self, outcome: AgendaProcessingResult) -> str:
        if outcome.clarification_needed:
            return outcome.clarification_reply or (
                "Encontrei um possível compromisso, mas ainda preciso que você confirme a intenção, a data e o horário para salvar com segurança."
            )
        if outcome.saved_event is None:
            return "Recebi a mensagem. Tive sinal de agenda, mas não consegui consolidar o compromisso com segurança."

        event = outcome.saved_event
        status_label = "Firme" if event.status == "firme" else "Tentativo"
        event_time = self.agenda_guardian_service.format_local_datetime(event.inicio)
        reminder_rule = self.agenda_guardian_service.format_reminder_rule(event)
        origin_label = event.contato_origem or "não identificada"

        if outcome.action == "cancel":
            return (
                "*Compromisso removido da agenda*\n\n"
                f"*{event.titulo}*\n"
                f"• Horário anterior: {event_time}\n"
                f"• Origem: {origin_label}\n\n"
                "Se quiser, eu posso marcar outro horário no lugar."
            )
        if outcome.updated_existing_event:
            if outcome.action == "reschedule":
                return (
                    "*Compromisso reagendado*\n\n"
                    f"*{event.titulo}*\n"
                    f"• Novo horário: {event_time}\n"
                    f"• Status: {status_label}\n"
                    f"• Lembretes: {reminder_rule}\n"
                    f"• Origem: {origin_label}\n\n"
                    "Se quiser, eu também posso ajustar a duração ou a antecedência."
                )
            return (
                "*Lembrete atualizado na agenda*\n\n"
                f"*{event.titulo}*\n"
                f"• Quando: {event_time}\n"
                f"• Status: {status_label}\n"
                f"• Lembretes: {reminder_rule}\n"
                f"• Origem: {origin_label}\n\n"
                "Se quiser, eu também posso ajustar o horário ou a duração."
            )
        if outcome.conflict_event is not None:
            conflict_time = self.agenda_guardian_service.format_local_datetime(outcome.conflict_event.inicio)
            return (
                "*Compromisso salvo com atenção de conflito*\n\n"
                f"*{event.titulo}*\n"
                f"• Quando: {event_time}\n"
                f"• Status: {status_label}\n"
                f"• Lembretes: {reminder_rule}\n"
                f"• Origem: {origin_label}\n\n"
                "*Atenção*\n"
                f"Já existe \"{outcome.conflict_event.titulo}\" em {conflict_time}.\n\n"
                "Se quiser, eu posso te ajudar a reorganizar esse horário."
            )
        return (
            "*Compromisso salvo na agenda*\n\n"
            f"*{event.titulo}*\n"
            f"• Quando: {event_time}\n"
            f"• Status: {status_label}\n"
            f"• Lembretes: {reminder_rule}\n"
            f"• Origem: {origin_label}\n\n"
            "Se quiser, eu também posso ajustar antecedência, horário ou duração."
        )

    async def _learn_from_inbound_message(
        self,
        *,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        contact_memory: WhatsAppAgentContactMemoryRecord | None,
    ) -> AgentLearningOutcome:
        if not self._should_extract_agent_memory(inbound_message.content):
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                learning_status="not_relevant",
            )
            return AgentLearningOutcome(
                status="not_relevant",
                model_run_id=None,
                learned_at=None,
                memory=contact_memory,
                last_decision=None,
            )

        started = perf_counter()
        decision: DeepSeekAgentMemoryDecision | None = None
        error_text: str | None = None
        try:
            decision = await self.deepseek_service.extract_agent_memory(
                user_message=inbound_message.content,
                existing_memory_context=self._render_contact_memory_context(contact_memory),
            )
        except Exception as error:
            error_text = str(error)

        elapsed_ms = int((perf_counter() - started) * 1000)
        model_run = self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=None,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="whatsapp_agent_memory_extract",
            success=decision is not None,
            latency_ms=elapsed_ms,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=error_text,
            created_at=datetime.now(UTC),
        )
        model_run_id = model_run.id if model_run else None

        if decision is None:
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                learning_status="failed",
                model_run_id=model_run_id,
                error_text=error_text,
                metadata={
                    **inbound_message.metadata,
                    "learning_error": error_text,
                },
            )
            return AgentLearningOutcome(
                status="failed",
                model_run_id=model_run_id,
                learned_at=None,
                memory=contact_memory,
                last_decision=decision,
                error_text=error_text,
            )

        important_saved = self._persist_important_message_if_needed(
            inbound_message=inbound_message,
            thread=thread,
            decision=decision,
            saved_at=datetime.now(UTC),
        )
        learning_metadata = {
            **self._build_learning_metadata(decision),
            "agent_saved_as_important": important_saved,
        }

        if not self._decision_has_memory_update(decision):
            self.store.update_whatsapp_agent_message(
                message_id=inbound_message.id,
                learning_status="reviewed_no_update",
                model_run_id=model_run_id,
                metadata={
                    **inbound_message.metadata,
                    **learning_metadata,
                },
            )
            return AgentLearningOutcome(
                status="reviewed_no_update",
                model_run_id=model_run_id,
                learned_at=None,
                memory=contact_memory,
                last_decision=decision,
            )

        learned_at = datetime.now(UTC)
        updated_memory = self._persist_contact_memory(
            current=contact_memory,
            decision=decision,
            thread=thread,
            session=session,
            learned_at=learned_at,
        )
        self.store.update_whatsapp_agent_message(
            message_id=inbound_message.id,
            learning_status="learned",
            model_run_id=model_run_id,
            learned_at=learned_at,
            metadata={
                **inbound_message.metadata,
                **learning_metadata,
            },
        )
        return AgentLearningOutcome(
            status="learned",
            model_run_id=model_run_id,
            learned_at=learned_at,
            memory=updated_memory,
            last_decision=decision,
        )

    def _persist_contact_memory(
        self,
        *,
        current: WhatsAppAgentContactMemoryRecord | None,
        decision: DeepSeekAgentMemoryDecision,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        learned_at: datetime,
    ) -> WhatsAppAgentContactMemoryRecord:
        current_preferences = current.preferences if current is not None else []
        current_objectives = current.objectives if current is not None else []
        current_durable_facts = current.durable_facts if current is not None else []
        current_constraints = current.constraints if current is not None else []
        current_recurring = current.recurring_instructions if current is not None else []
        learned_message_count = (current.learned_message_count if current is not None else 0) + 1

        return self.store.upsert_whatsapp_agent_contact_memory(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=thread.contact_phone or session.contact_phone or "",
            chat_jid=thread.chat_jid or session.chat_jid,
            contact_name=thread.contact_name,
            profile_summary=self._merge_profile_summary(
                current.profile_summary if current is not None else "",
                decision.profile_summary,
            ),
            preferred_tone=(decision.preferred_tone or (current.preferred_tone if current is not None else "")).strip(),
            preferences=self.store._merge_unique_string_lists(current_preferences, decision.preferences, limit=10),
            objectives=self.store._merge_unique_string_lists(current_objectives, decision.objectives, limit=10),
            durable_facts=self.store._merge_unique_string_lists(current_durable_facts, decision.durable_facts, limit=12),
            constraints=self.store._merge_unique_string_lists(current_constraints, decision.constraints, limit=10),
            recurring_instructions=self.store._merge_unique_string_lists(current_recurring, decision.recurring_instructions, limit=10),
            learned_message_count=learned_message_count,
            last_learned_at=learned_at,
            updated_at=learned_at,
            )

    def _persist_important_message_if_needed(
        self,
        *,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        decision: DeepSeekAgentMemoryDecision,
        saved_at: datetime,
    ) -> bool:
        if not decision.should_save_as_important:
            return False
        reason = decision.importance_reason.strip()
        if not reason:
            return False
        confidence = max(0, min(100, int(decision.importance_confidence or 0)))
        if confidence <= 0:
            confidence = 72
        saved = self.store.upsert_important_messages(
            user_id=self.settings.default_user_id,
            messages=[
                ImportantMessageSeed(
                    source_message_id=inbound_message.id,
                    contact_name=thread.contact_name or inbound_message.contact_phone or "Contato",
                    contact_phone=inbound_message.contact_phone,
                    direction=inbound_message.direction or "inbound",
                    message_text=inbound_message.content,
                    message_timestamp=inbound_message.message_timestamp,
                    category=decision.importance_category,
                    importance_reason=reason,
                    confidence=confidence,
                )
            ],
            saved_at=saved_at,
        )
        return saved > 0

    def _merge_profile_summary(self, current_summary: str, incoming_summary: str) -> str:
        current = current_summary.strip()
        incoming = incoming_summary.strip()
        if not incoming:
            return current
        if not current:
            return incoming
        if incoming.casefold() in current.casefold():
            return current
        if current.casefold() in incoming.casefold():
            return incoming
        return f"{incoming} {current}".strip()[:600]

    def _decision_has_memory_update(self, decision: DeepSeekAgentMemoryDecision) -> bool:
        return bool(
            decision.should_update
            and (
                decision.profile_summary
                or decision.preferred_tone
                or decision.preferences
                or decision.objectives
                or decision.durable_facts
                or decision.constraints
                or decision.recurring_instructions
            )
        )

    def _build_learning_metadata(self, decision: DeepSeekAgentMemoryDecision) -> dict[str, object]:
        return {
            "learning_explanation": decision.explanation,
            "agent_mood_signals": decision.mood_signals[:4],
            "agent_implied_urgency": decision.implied_urgency,
            "agent_implied_tasks": decision.implied_tasks[:4],
            "agent_important_reason": decision.importance_reason if decision.should_save_as_important else "",
            "agent_important_category": decision.importance_category if decision.should_save_as_important else "",
            "agent_important_confidence": decision.importance_confidence if decision.should_save_as_important else 0,
        }

    def _should_extract_agent_memory(self, message_text: str) -> bool:
        normalized = " ".join(message_text.lower().split()).strip()
        if len(normalized) < 14:
            return False
        keywords = (
            "eu ",
            "meu ",
            "minha ",
            "prefiro",
            "gosto",
            "nao gosto",
            "quero",
            "preciso",
            "me lembra",
            "me chame",
            "me chama",
            "evite",
            "sempre",
            "nunca",
            "normalmente",
            "costumo",
            "objetivo",
            "meta",
            "restricao",
            "prioridade",
            "trabalho com",
            "sou ",
        )
        return any(keyword in normalized for keyword in keywords)

    def _build_rich_contact_context(
        self,
        *,
        memory: WhatsAppAgentContactMemoryRecord | None,
        learning_outcome: AgentLearningOutcome,
    ) -> str:
        base = self._render_contact_memory_context(memory)
        parts: list[str] = [base] if base else []

        # Inject real-time signals from the latest learning extraction
        decision = learning_outcome.last_decision

        if decision is not None:
            if decision.mood_signals:
                parts.append(f"Humor/estado emocional atual: {'; '.join(decision.mood_signals[:4])}")
            if decision.implied_urgency:
                parts.append(f"Urgencia detectada: {decision.implied_urgency}")
            if decision.mentioned_relationships:
                parts.append(f"Relacionamentos mencionados: {'; '.join(decision.mentioned_relationships[:4])}")
            if decision.implied_tasks:
                parts.append(f"Acoes esperadas: {'; '.join(decision.implied_tasks[:4])}")
            if decision.writing_style_hints:
                parts.append(f"Estilo de escrita: {decision.writing_style_hints}")

        return "\n".join(p for p in parts if p).strip()

    def _render_contact_memory_context(self, memory: WhatsAppAgentContactMemoryRecord | None) -> str:
        if memory is None:
            return ""

        parts: list[str] = []
        if memory.profile_summary:
            parts.append(f"Resumo deste dono no agente: {memory.profile_summary}")
        if memory.preferred_tone:
            parts.append(f"Tom preferido: {memory.preferred_tone}")
        if memory.preferences:
            parts.append(f"Preferencias: {'; '.join(memory.preferences[:6])}")
        if memory.objectives:
            parts.append(f"Objetivos recorrentes: {'; '.join(memory.objectives[:6])}")
        if memory.durable_facts:
            parts.append(f"Fatos duraveis: {'; '.join(memory.durable_facts[:6])}")
        if memory.constraints:
            parts.append(f"Restricoes: {'; '.join(memory.constraints[:6])}")
        if memory.recurring_instructions:
            parts.append(f"Instrucoes recorrentes: {'; '.join(memory.recurring_instructions[:6])}")
        return "\n".join(parts).strip()

    def _sync_settings_with_observer(self, _observer_status: ObserverStatusResponse) -> WhatsAppAgentSettingsRecord:
        return self.store.get_whatsapp_agent_settings(self.settings.default_user_id)

    def _build_status_response(
        self,
        *,
        agent_status: ObserverStatusResponse,
        settings: WhatsAppAgentSettingsRecord,
    ) -> WhatsAppAgentStatusResponse:
        return WhatsAppAgentStatusResponse(
            instance_name=agent_status.instance_name,
            connected=agent_status.connected,
            state=agent_status.state,
            gateway_ready=agent_status.gateway_ready,
            auto_reply_enabled=settings.auto_reply_enabled,
            owner_number=agent_status.owner_number,
            reply_scope="observer_owner_only",
            qr_code=agent_status.qr_code,
            qr_expires_in_sec=agent_status.qr_expires_in_sec,
            last_seen_at=agent_status.last_seen_at,
            last_error=agent_status.last_error,
        )

    def _build_settings_response(self, settings_record: WhatsAppAgentSettingsRecord) -> WhatsAppAgentSettingsResponse:
        return WhatsAppAgentSettingsResponse(
            user_id=str(settings_record.user_id),
            auto_reply_enabled=settings_record.auto_reply_enabled,
            reply_scope="observer_owner_only",
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
