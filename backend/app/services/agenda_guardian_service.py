from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.deepseek_service import DeepSeekAgendaExtractionResult, DeepSeekService
from app.services.observer_gateway import ObserverGatewayService
from app.services.supabase_store import AgendaEventRecord, IngestedMessageRecord, SupabaseStore

DEFAULT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
DEFAULT_EVENT_DURATION = timedelta(hours=1)
logger = logging.getLogger("auracore.agenda_guardian")

DATE_SIGNAL_REGEX = re.compile(
    r"\b(?:hoje|amanh[aã]|depois de amanh[aã]|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo|"
    r"semana que vem|pr[oó]xima semana|dia\s+\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"[àa]s?\s*\d{1,2}(?::\d{2})?\s*h?|\d{1,2}:\d{2}|\d{1,2}h(?:\d{2})?)\b",
    re.IGNORECASE,
)
CONFIRMED_REGEX = re.compile(r"\b(?:fechado|confirmado|confirmada|bora|combinado|marcado|certo)\b", re.IGNORECASE)
TENTATIVE_REGEX = re.compile(r"\b(?:talvez|vou tentar|tentar|se der|acho que|possivelmente)\b", re.IGNORECASE)


@dataclass(slots=True)
class AgendaProcessingResult:
    detected: bool = False
    saved_event: AgendaEventRecord | None = None
    conflict_event: AgendaEventRecord | None = None
    alert_sent: bool = False
    skipped_reason: str | None = None


class AgendaGuardianService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        deepseek_service: DeepSeekService,
        observer_gateway: ObserverGatewayService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service
        self.observer_gateway = observer_gateway

    async def process_message(self, *, message: IngestedMessageRecord) -> AgendaProcessingResult:
        if message.chat_type != "direct":
            return AgendaProcessingResult(skipped_reason="non_direct")

        if self.store.get_agenda_event_by_message_id(user_id=message.user_id, message_id=message.message_id):
            return AgendaProcessingResult(skipped_reason="duplicate_message")

        normalized_text = " ".join(message.message_text.split()).strip()
        if not normalized_text:
            return AgendaProcessingResult(skipped_reason="empty_text")
        if not self._has_schedule_signal(normalized_text):
            return AgendaProcessingResult(skipped_reason="no_schedule_signal")

        await self._log_debug(
            f"[Guardião do Tempo] Sinal temporal detectado em mensagem de {message.contact_name}: {normalized_text}"
        )

        try:
            extraction = await self.deepseek_service.extract_agenda_signal(
                message_text=normalized_text,
                reference_now=message.timestamp.astimezone(DEFAULT_TIMEZONE),
            )
        except Exception as exc:
            await self._log_debug(f"[Guardião do Tempo] Falha na extração estruturada: {str(exc)}")
            logger.warning("agenda_extraction_failed message_id=%s detail=%s", message.message_id, str(exc))
            return AgendaProcessingResult(skipped_reason="extract_failed")

        if not extraction.has_schedule_signal or not extraction.data_inicio:
            return AgendaProcessingResult(skipped_reason="no_structured_schedule")

        resolved_status = self._resolve_status(extraction=extraction, source_text=normalized_text)
        inicio = self._normalize_datetime(extraction.data_inicio, reference=message.timestamp)
        if inicio is None:
            await self._log_debug("[Guardião do Tempo] Extração retornou data_inicio inválida.")
            return AgendaProcessingResult(skipped_reason="invalid_start")
        fim = self._normalize_datetime(extraction.data_fim, reference=message.timestamp)
        if fim is None or fim <= inicio:
            fim = inicio + DEFAULT_EVENT_DURATION

        titulo = extraction.titulo.strip() if extraction.titulo.strip() else self._fallback_title(normalized_text)
        await self._log_debug(
            f"[Guardião do Tempo] Extração válida: '{titulo}' em {self._format_local(inicio)} ({resolved_status})."
        )

        conflicts = self.store.find_agenda_conflicts(
            user_id=message.user_id,
            inicio=inicio,
            fim=fim,
            exclude_message_id=message.message_id,
            limit=1,
        )
        saved_event = self.store.upsert_agenda_event(
            user_id=message.user_id,
            titulo=titulo,
            inicio=inicio,
            fim=fim,
            status=resolved_status,
            contato_origem=message.contact_name,
            message_id=message.message_id,
        )
        await self._log_debug(
            f"[Guardião do Tempo] Compromisso salvo: '{saved_event.titulo}' de {self._format_local(saved_event.inicio)} até {self._format_local(saved_event.fim)}."
        )

        conflict_event = conflicts[0] if conflicts else None
        alert_sent = False
        if conflict_event is not None:
            await self._log_debug(
                f"[Guardião do Tempo] Conflito detectado com '{conflict_event.titulo}' em {self._format_local(conflict_event.inicio)}."
            )
            alert_sent = await self._send_conflict_alert(new_event=saved_event, existing_event=conflict_event)

        return AgendaProcessingResult(
            detected=True,
            saved_event=saved_event,
            conflict_event=conflict_event,
            alert_sent=alert_sent,
        )

    def _has_schedule_signal(self, text: str) -> bool:
        return bool(DATE_SIGNAL_REGEX.search(text))

    def _resolve_status(self, *, extraction: DeepSeekAgendaExtractionResult, source_text: str) -> str:
        extracted_intention = (extraction.intencao or "").strip().lower()
        if extracted_intention == "confirmado":
            return "firme"
        if extracted_intention in {"tentativo", "incerto"}:
            return "tentativo"
        if CONFIRMED_REGEX.search(source_text):
            return "firme"
        if TENTATIVE_REGEX.search(source_text):
            return "tentativo"
        return "tentativo"

    def _normalize_datetime(self, raw_value: str | None, *, reference: datetime) -> datetime | None:
        value = (raw_value or "").strip()
        if not value:
            return None

        parsed = self._parse_iso_datetime(value)
        if parsed is None:
            parsed = self._parse_dateparser_datetime(value, reference=reference)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=DEFAULT_TIMEZONE)
        return parsed.astimezone(UTC)

    def _parse_iso_datetime(self, value: str) -> datetime | None:
        candidates = [value]
        if value.endswith("Z"):
            candidates.append(value.replace("Z", "+00:00"))
        for candidate in candidates:
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    def _parse_dateparser_datetime(self, value: str, *, reference: datetime) -> datetime | None:
        try:
            import dateparser
        except Exception:
            return None
        return dateparser.parse(
            value,
            languages=["pt", "en"],
            settings={
                "TIMEZONE": str(DEFAULT_TIMEZONE),
                "TO_TIMEZONE": str(DEFAULT_TIMEZONE),
                "RETURN_AS_TIMEZONE_AWARE": True,
                "RELATIVE_BASE": reference.astimezone(DEFAULT_TIMEZONE),
                "PREFER_DATES_FROM": "future",
            },
        )

    async def _send_conflict_alert(self, *, new_event: AgendaEventRecord, existing_event: AgendaEventRecord) -> bool:
        owner_phone: str | None = None
        try:
            observer_status = await self.observer_gateway.get_observer_status(refresh_qr=False)
            owner_phone = (observer_status.owner_number or "").strip() or None
        except Exception:
            owner_phone = None
        if not owner_phone:
            owner_phone = self.store.get_whatsapp_session_owner_phone(session_id=f"{self.settings.default_user_id}:observer")
            if owner_phone and not owner_phone.startswith("55"):
                owner_phone = f"55{owner_phone}"
        if not owner_phone:
            await self._log_debug("[Guardião do Tempo] Conflito detectado, mas o número conectado não foi localizado.")
            return False
        message_text = (
            "⚠️ AuraCore: Possível Conflito detectado!\n"
            f"Álvaro, você está combinando '{new_event.titulo}' para {self._format_local(new_event.inicio)}, "
            f"mas já possui '{existing_event.titulo}' agendado para este mesmo horário.\n"
            "Deseja sugerir outro horário ou manter ambos?"
        )
        try:
            await self.observer_gateway.send_text_message(chat_jid=owner_phone, message_text=message_text)
            await self._log_debug("[Guardião do Tempo] Alerta de conflito enviado ao WhatsApp do dono.")
            return True
        except Exception as exc:
            await self._log_debug(f"[Guardião do Tempo] Falha ao enviar alerta: {str(exc)}")
            logger.warning(
                "agenda_conflict_alert_failed message_id=%s conflict_message_id=%s detail=%s",
                new_event.message_id,
                existing_event.message_id,
                str(exc),
            )
            return False

    async def _log_debug(self, content: str) -> None:
        thread = self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)
        self.store.append_chat_message(
            thread_id=thread.id,
            role="assistant",
            content=content,
            created_at=datetime.now(UTC),
        )

    def _fallback_title(self, text: str) -> str:
        compact = " ".join(text.split()).strip()
        return compact[:120] if compact else "Compromisso"

    def _format_local(self, value: datetime) -> str:
        localized = value.astimezone(DEFAULT_TIMEZONE)
        return localized.strftime("%d/%m/%Y às %H:%M")
