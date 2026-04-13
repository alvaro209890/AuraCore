from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.deepseek_service import DeepSeekAgendaExtractionResult, DeepSeekService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.supabase_store import AgendaEventRecord, IngestedMessageRecord, SupabaseStore

DEFAULT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
DEFAULT_EVENT_DURATION = timedelta(hours=1)
REMINDER_LOOP_INTERVAL_SECONDS = 30
REMINDER_LOOKAHEAD_SECONDS = 60
STALE_REMINDER_SUPPRESSION_HOURS = 6
logger = logging.getLogger("auracore.agenda_guardian")

DATE_SIGNAL_REGEX = re.compile(
    r"\b(?:hoje|amanh[aã]|depois de amanh[aã]|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo|"
    r"semana que vem|pr[oó]xima semana|dia\s+\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"[àa]s?\s*\d{1,2}(?::\d{2})?\s*h?|\d{1,2}:\d{2}|\d{1,2}h(?:\d{2})?)\b",
    re.IGNORECASE,
)
CONFIRMED_REGEX = re.compile(r"\b(?:fechado|confirmado|confirmada|bora|combinado|marcado|certo)\b", re.IGNORECASE)
TENTATIVE_REGEX = re.compile(r"\b(?:talvez|vou tentar|tentar|se der|acho que|possivelmente)\b", re.IGNORECASE)
REMINDER_OFFSET_REGEXES = [
    re.compile(
        r"\b(?:me\s+)?(?:avise|avisa|avisar|lembre|lembra|lembrar)(?:\s+de)?(?:\s+com)?\s+"
        r"(?P<amount>\d{1,4}|uma|um|meia)\s*"
        r"(?P<unit>min(?:uto)?s?|h(?:ora)?s?|dia?s?)\s+"
        r"(?:antes|de\s+anteced[eê]ncia)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:com\s+)?(?P<amount>\d{1,4}|uma|um|meia)\s*"
        r"(?P<unit>min(?:uto)?s?|h(?:ora)?s?|dia?s?)\s+"
        r"(?:de\s+)?anteced[eê]ncia\b",
        re.IGNORECASE,
    ),
]


@dataclass(slots=True)
class AgendaProcessingResult:
    detected: bool = False
    saved_event: AgendaEventRecord | None = None
    conflict_event: AgendaEventRecord | None = None
    alert_sent: bool = False
    reminder_offset_minutes: int = 0
    skipped_reason: str | None = None


class AgendaGuardianService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        deepseek_service: DeepSeekService,
        observer_gateway: ObserverGatewayService,
        agent_gateway: WhatsAppAgentGatewayService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service
        self.observer_gateway = observer_gateway
        self.agent_gateway = agent_gateway
        self._reminder_task: asyncio.Task[None] | None = None
        self._reminder_lock = asyncio.Lock()

    def warm_start(self) -> None:
        existing = self._reminder_task
        if existing is not None and not existing.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("agenda_reminder_loop_not_started user_id=%s reason=no_running_loop", self.settings.default_user_id)
            return
        self._reminder_task = loop.create_task(
            self._schedule_reminder_loop(),
            name=f"agenda-reminders-{self.settings.default_user_id}",
        )

    async def process_message(self, *, message: IngestedMessageRecord) -> AgendaProcessingResult:
        if message.chat_type != "direct":
            return AgendaProcessingResult(skipped_reason="non_direct")
        return await self._process_candidate(
            user_id=message.user_id,
            message_id=message.message_id,
            contact_name=message.contact_name,
            message_text=message.message_text,
            occurred_at=message.timestamp,
            source_label=f"Observador/{message.contact_name}",
            should_send_conflict_alert=True,
        )

    async def process_agent_message(
        self,
        *,
        user_id: UUID,
        message_id: str,
        contact_name: str,
        message_text: str,
        occurred_at: datetime,
    ) -> AgendaProcessingResult:
        return await self._process_candidate(
            user_id=user_id,
            message_id=message_id,
            contact_name=contact_name,
            message_text=message_text,
            occurred_at=occurred_at,
            source_label=f"Agente/{contact_name}",
            should_send_conflict_alert=False,
        )

    async def process_due_reminders(self) -> None:
        async with self._reminder_lock:
            now = datetime.now(UTC)
            due_before = now + timedelta(seconds=REMINDER_LOOKAHEAD_SECONDS)
            stale_cutoff = now - timedelta(hours=STALE_REMINDER_SUPPRESSION_HOURS)
            due_pre_events = self.store.list_due_agenda_pre_reminders(
                user_id=self.settings.default_user_id,
                due_before=due_before,
                limit=20,
            )
            for event in due_pre_events:
                if event.pre_reminder_sent_at is not None or event.reminder_offset_minutes <= 0:
                    continue
                if event.inicio <= now:
                    self.store.mark_agenda_event_pre_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=now,
                    )
                    await self._log_debug(
                        f"[Guardião do Tempo] Lembrete antecipado suprimido para '{event.titulo}' porque o horário já chegou."
                    )
                    continue
                sent = await self._send_due_reminder(event=event, phase="pre")
                if sent:
                    self.store.mark_agenda_event_pre_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=datetime.now(UTC),
                    )
            due_events = self.store.list_due_agenda_events(
                user_id=self.settings.default_user_id,
                due_before=due_before,
                limit=20,
            )
            for event in due_events:
                if event.reminder_sent_at is not None:
                    continue
                if event.inicio < stale_cutoff:
                    self.store.mark_agenda_event_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=now,
                    )
                    await self._log_debug(
                        f"[Guardião do Tempo] Lembrete retroativo suprimido para '{event.titulo}' ({self._format_local(event.inicio)})."
                    )
                    continue
                sent = await self._send_due_reminder(event=event, phase="start")
                if sent:
                    self.store.mark_agenda_event_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=datetime.now(UTC),
                    )

    async def _schedule_reminder_loop(self) -> None:
        while True:
            try:
                await self.process_due_reminders()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("agenda_reminder_loop_failed user_id=%s detail=%s", self.settings.default_user_id, str(exc))
                await self._log_debug(f"[Guardião do Tempo] Falha no loop de lembretes: {str(exc)}")
            await asyncio.sleep(REMINDER_LOOP_INTERVAL_SECONDS)

    async def _process_candidate(
        self,
        *,
        user_id: UUID,
        message_id: str,
        contact_name: str,
        message_text: str,
        occurred_at: datetime,
        source_label: str,
        should_send_conflict_alert: bool,
    ) -> AgendaProcessingResult:
        if self.store.get_agenda_event_by_message_id(user_id=user_id, message_id=message_id):
            return AgendaProcessingResult(skipped_reason="duplicate_message")

        normalized_text = " ".join(message_text.split()).strip()
        if not normalized_text:
            return AgendaProcessingResult(skipped_reason="empty_text")
        if not self._has_schedule_signal(normalized_text):
            return AgendaProcessingResult(skipped_reason="no_schedule_signal")

        await self._log_debug(
            f"[Guardião do Tempo] Sinal temporal detectado em {source_label}: {normalized_text}"
        )

        try:
            extraction = await self.deepseek_service.extract_agenda_signal(
                message_text=normalized_text,
                reference_now=occurred_at.astimezone(DEFAULT_TIMEZONE),
            )
        except Exception as exc:
            await self._log_debug(f"[Guardião do Tempo] Falha na extração estruturada: {str(exc)}")
            logger.warning("agenda_extraction_failed message_id=%s detail=%s", message_id, str(exc))
            return AgendaProcessingResult(skipped_reason="extract_failed")

        if not extraction.has_schedule_signal or not extraction.data_inicio:
            return AgendaProcessingResult(skipped_reason="no_structured_schedule")

        resolved_status = self._resolve_status(extraction=extraction, source_text=normalized_text)
        reminder_offset_minutes = self._extract_reminder_offset_minutes(normalized_text)
        inicio = self._normalize_datetime(extraction.data_inicio, reference=occurred_at)
        if inicio is None:
            await self._log_debug("[Guardião do Tempo] Extração retornou data_inicio inválida.")
            return AgendaProcessingResult(skipped_reason="invalid_start")
        fim = self._normalize_datetime(extraction.data_fim, reference=occurred_at)
        if fim is None or fim <= inicio:
            fim = inicio + DEFAULT_EVENT_DURATION

        titulo = extraction.titulo.strip() if extraction.titulo.strip() else self._fallback_title(normalized_text)
        await self._log_debug(
            f"[Guardião do Tempo] Extração válida: '{titulo}' em {self._format_local(inicio)} ({resolved_status})."
        )

        conflicts = self.store.find_agenda_conflicts(
            user_id=user_id,
            inicio=inicio,
            fim=fim,
            exclude_message_id=message_id,
            limit=1,
        )
        saved_event = self.store.upsert_agenda_event(
            user_id=user_id,
            titulo=titulo,
            inicio=inicio,
            fim=fim,
            status=resolved_status,
            contato_origem=contact_name,
            message_id=message_id,
            reminder_offset_minutes=reminder_offset_minutes,
        )
        await self._log_debug(
            f"[Guardião do Tempo] Compromisso salvo: '{saved_event.titulo}' de {self._format_local(saved_event.inicio)} até {self._format_local(saved_event.fim)}."
        )
        if reminder_offset_minutes > 0:
            await self._log_debug(
                f"[Guardião do Tempo] Lembrete antecipado configurado para {reminder_offset_minutes} minuto(s) antes, em horário de Brasília."
            )

        conflict_event = conflicts[0] if conflicts else None
        alert_sent = False
        if conflict_event is not None:
            await self._log_debug(
                f"[Guardião do Tempo] Conflito detectado com '{conflict_event.titulo}' em {self._format_local(conflict_event.inicio)}."
            )
            if should_send_conflict_alert:
                alert_sent = await self._send_conflict_alert(new_event=saved_event, existing_event=conflict_event)

        return AgendaProcessingResult(
            detected=True,
            saved_event=saved_event,
            conflict_event=conflict_event,
            alert_sent=alert_sent,
            reminder_offset_minutes=reminder_offset_minutes,
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
        owner_target = await self._resolve_owner_chat_target(preferred_channel="observer")
        if not owner_target:
            await self._log_debug("[Guardião do Tempo] Conflito detectado, mas o número conectado não foi localizado.")
            return False
        message_text = (
            "⚠️ AuraCore: Possível Conflito detectado!\n"
            f"Álvaro, você está combinando '{new_event.titulo}' para {self._format_local(new_event.inicio)}, "
            f"mas já possui '{existing_event.titulo}' agendado para este mesmo horário.\n"
            "Deseja sugerir outro horário ou manter ambos?"
        )
        try:
            await self.observer_gateway.send_text_message(chat_jid=owner_target, message_text=message_text)
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

    async def _send_due_reminder(self, *, event: AgendaEventRecord, phase: str) -> bool:
        owner_target = await self._resolve_owner_chat_target(preferred_channel="agent")
        if not owner_target:
            await self._log_debug(
                f"[Guardião do Tempo] Lembrete de '{event.titulo}' não pôde ser entregue porque o número conectado não foi localizado."
            )
            return False

        status_label = "Firme" if event.status == "firme" else "Tentativo"
        if phase == "pre":
            message_text = (
                f"⏰ AuraCore: Lembrete antecipado de '{event.titulo}'.\n"
                f"Começa em {event.reminder_offset_minutes} minuto(s), às {self._format_local(event.inicio)}.\n"
                f"Status: {status_label}\n"
                f"Origem: {event.contato_origem or 'não identificada'}\n"
                "Horário de Brasília."
            )
        else:
            message_text = (
                f"⏰ AuraCore: Chegou o horário de '{event.titulo}'.\n"
                f"Início: {self._format_local(event.inicio)}\n"
                f"Status: {status_label}\n"
                f"Origem: {event.contato_origem or 'não identificada'}\n"
                "Horário de Brasília."
            )

        try:
            await self.agent_gateway.send_text_message(chat_jid=owner_target, message_text=message_text)
            await self._log_debug(
                f"[Guardião do Tempo] Lembrete {'antecipado' if phase == 'pre' else 'no horário'} enviado para '{event.titulo}'."
            )
            return True
        except Exception as agent_exc:
            logger.warning("agenda_due_reminder_agent_failed event_id=%s detail=%s", event.id, str(agent_exc))
            try:
                await self.observer_gateway.send_text_message(chat_jid=owner_target, message_text=message_text)
                await self._log_debug(
                    f"[Guardião do Tempo] Lembrete {'antecipado' if phase == 'pre' else 'no horário'} enviado via observador para '{event.titulo}'."
                )
                return True
            except Exception as observer_exc:
                await self._log_debug(
                    f"[Guardião do Tempo] Falha ao enviar lembrete de '{event.titulo}': {str(observer_exc)}"
                )
                logger.warning(
                    "agenda_due_reminder_failed event_id=%s detail=%s fallback_detail=%s",
                    event.id,
                    str(agent_exc),
                    str(observer_exc),
                )
                return False

    async def _resolve_owner_chat_target(self, *, preferred_channel: str) -> str | None:
        attempts: list[tuple[str, str]] = []
        if preferred_channel == "agent":
            attempts.extend(
                [
                    ("agent_status", "agent"),
                    ("agent_session", "agent"),
                    ("observer_status", "observer"),
                    ("observer_session", "observer"),
                ]
            )
        else:
            attempts.extend(
                [
                    ("observer_status", "observer"),
                    ("observer_session", "observer"),
                    ("agent_status", "agent"),
                    ("agent_session", "agent"),
                ]
            )

        for source_kind, channel in attempts:
            target: str | None = None
            try:
                if source_kind == "agent_status":
                    target = self._normalize_chat_target((await self.agent_gateway.get_agent_status()).owner_number)
                elif source_kind == "observer_status":
                    target = self._normalize_chat_target((await self.observer_gateway.get_observer_status(refresh_qr=False)).owner_number)
                elif source_kind == "agent_session":
                    target = self._normalize_chat_target(
                        self.store.get_whatsapp_session_owner_phone(session_id=f"{self.settings.default_user_id}:agent")
                    )
                elif source_kind == "observer_session":
                    target = self._normalize_chat_target(
                        self.store.get_whatsapp_session_owner_phone(session_id=f"{self.settings.default_user_id}:observer")
                    )
            except Exception:
                target = None
            if target:
                logger.info(
                    "agenda_owner_target_resolved user_id=%s channel=%s source=%s",
                    self.settings.default_user_id,
                    channel,
                    source_kind,
                )
                return target
        return None

    def _normalize_chat_target(self, value: str | None) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None
        if "@" in raw:
            return raw
        digits = "".join(char for char in raw if char.isdigit())
        if not digits:
            return None
        if len(digits) >= 12 and digits.startswith("55"):
            return digits
        if 10 <= len(digits) <= 11:
            return f"55{digits}"
        return digits

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

    def _extract_reminder_offset_minutes(self, text: str) -> int:
        compact = " ".join(text.split()).strip().lower()
        if not compact:
            return 0
        for pattern in REMINDER_OFFSET_REGEXES:
            match = pattern.search(compact)
            if not match:
                continue
            amount = self._parse_reminder_amount(match.group("amount"))
            unit = (match.group("unit") or "").strip().lower()
            if amount <= 0:
                continue
            if unit.startswith("min"):
                return min(amount, 10080)
            if unit.startswith("h"):
                return min(amount * 60, 10080)
            if unit.startswith("dia"):
                return min(amount * 24 * 60, 10080)
        return 0

    def _parse_reminder_amount(self, raw_value: str | None) -> int:
        value = (raw_value or "").strip().lower()
        if not value:
            return 0
        if value == "meia":
            return 30
        if value in {"uma", "um"}:
            return 1
        try:
            return max(0, int(value))
        except ValueError:
            return 0

    def format_reminder_rule(self, event: AgendaEventRecord) -> str:
        if event.reminder_offset_minutes > 0:
            pre_time = event.inicio - timedelta(minutes=event.reminder_offset_minutes)
            return (
                f"{event.reminder_offset_minutes} minuto(s) antes em {self._format_local(pre_time)} "
                "e novamente no horário de Brasília"
            )
        return "Somente no horário de Brasília"

    def format_local_datetime(self, value: datetime) -> str:
        return self._format_local(value)

    def _format_local(self, value: datetime) -> str:
        localized = value.astimezone(DEFAULT_TIMEZONE)
        return localized.strftime("%d/%m/%Y às %H:%M")
