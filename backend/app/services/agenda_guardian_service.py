from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.deepseek_service import (
    DeepSeekAgendaConflictResolutionResult,
    DeepSeekAgendaExtractionResult,
    DeepSeekService,
)
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
EVENT_KEYWORD_REGEX = re.compile(
    r"\b(?:agenda|agendar|agendado|agendada|marcar|marcado|marcada|reuni[aã]o|encontro|consulta|call|"
    r"visita|compromisso|entrevista|aula|almo[cç]o|caf[eé]|demo|demonstra[cç][aã]o)\b",
    re.IGNORECASE,
)
EXPLICIT_SCHEDULING_INTENT_REGEX = re.compile(
    r"\b(?:"
    r"agenda(?:r|do|da)?|marc(?:ar|a|ado|ada)|"
    r"remarc(?:ar|a|ado|ada)|reagend(?:ar|a|ado|ada)|"
    r"cancel(?:ar|a|ado|ada)|desmarc(?:ar|a|ado|ada)|"
    r"lembra(?:r|do)?|lembrete|avisa(?:r)?|"
    r"reuni[aã]o|consulta|entrevista|compromisso|call|demo|aula|encontro|visita"
    r")\b",
    re.IGNORECASE,
)
TIME_ONLY_CONTEXT_REGEX = re.compile(
    r"\b(?:tenho|tem|t[eê]m|vou ter|preciso ir|preciso estar|come[cç]a|inicia|e[áa]|ser[aá])\b",
    re.IGNORECASE,
)
AGENDA_HIGH_CONFIDENCE_THRESHOLD = 72
AGENDA_CLARIFY_CONFIDENCE_THRESHOLD = 45
GENERIC_TITLES = {"compromisso", "evento", "agenda", "horario", "horário"}
CONFIRMED_REGEX = re.compile(r"\b(?:fechado|confirmado|confirmada|bora|combinado|marcado|certo)\b", re.IGNORECASE)
TENTATIVE_REGEX = re.compile(r"\b(?:talvez|vou tentar|tentar|se der|acho que|possivelmente)\b", re.IGNORECASE)
CANCEL_ACTION_REGEX = re.compile(
    r"\b(?:cancel[aeiou]\w*|desmarc[aeiou]\w*|remov[aeiou]\w*|tir[aeiou]\w*\s+da\s+agenda|"
    r"nao\s+vai\s+dar|n[aã]o\s+vai\s+rolar|preciso\s+cancelar)\b",
    re.IGNORECASE,
)
RESCHEDULE_ACTION_REGEX = re.compile(
    r"\b(?:remarc[aeiou]\w*|reagend[aeiou]\w*|mud[aeiou]\w*\s+(?:para|pra)|"
    r"pass[aeiou]\w*\s+(?:para|pra)|jog[aeiou]\w*\s+(?:para|pra)|"
    r"troc[aeiou]\w*\s+o\s+hor[aá]rio|adi[aeiou]\w*)\b",
    re.IGNORECASE,
)
NEW_EVENT_HINT_REGEX = re.compile(
    r"\b(?:novo|nova|outro|outra|mais\s+um|mais\s+uma)\b",
    re.IGNORECASE,
)
DURATION_REGEXES = [
    re.compile(
        r"\b(?:por|durante)\s+(?P<amount>\d{1,4}|uma|um|meia)\s*(?P<unit>min(?:uto)?s?|h(?:ora)?s?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<amount>\d{1,4})\s*(?P<unit>min(?:uto)?s?|h(?:ora)?s?)\s+de\s+dura[cç][aã]o\b",
        re.IGNORECASE,
    ),
]
TITLE_TOKEN_REGEX = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
TITLE_STOPWORDS = {
    "agenda",
    "amanha",
    "amanhã",
    "antecedencia",
    "às",
    "as",
    "aula",
    "avisa",
    "call",
    "com",
    "compromisso",
    "consulta",
    "de",
    "demo",
    "dia",
    "duracao",
    "duração",
    "encontro",
    "entrevista",
    "hoje",
    "horario",
    "horário",
    "lembra",
    "lembrete",
    "marcar",
    "marcado",
    "marcada",
    "nova",
    "novo",
    "outro",
    "outra",
    "para",
    "pra",
    "proxima",
    "próxima",
    "reagendar",
    "remarcar",
    "reuniao",
    "reunião",
    "sexta",
    "segunda",
    "semana",
    "terca",
    "terça",
    "quinta",
    "quarta",
    "sabado",
    "sábado",
    "domingo",
}
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
    action: str = "none"
    saved_event: AgendaEventRecord | None = None
    conflict_event: AgendaEventRecord | None = None
    alert_sent: bool = False
    reminder_offset_minutes: int = 0
    updated_existing_event: bool = False
    clarification_needed: bool = False
    clarification_reply: str | None = None
    skipped_reason: str | None = None


@dataclass(slots=True)
class AgendaConflictResolutionOutcome:
    handled: bool = False
    applied: bool = False
    decision: str = "clarify"
    assistant_reply: str | None = None
    pending_alert_message_id: str | None = None
    new_event: AgendaEventRecord | None = None
    existing_event: AgendaEventRecord | None = None
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
            now_brasilia = datetime.now(DEFAULT_TIMEZONE)
            now = now_brasilia.astimezone(UTC)
            due_before = (now_brasilia + timedelta(seconds=REMINDER_LOOKAHEAD_SECONDS)).astimezone(UTC)
            stale_cutoff = now - timedelta(hours=STALE_REMINDER_SUPPRESSION_HOURS)
            due_pre_events = self.store.list_due_agenda_pre_reminders(
                user_id=self.settings.default_user_id,
                due_before=due_before,
                limit=20,
            )
            for event in due_pre_events:
                if event.pre_reminder_sent_at is not None or event.reminder_offset_minutes <= 0:
                    continue
                if event.status != "firme":
                    self.store.mark_agenda_event_pre_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=now,
                    )
                    self._log_debug(
                        f"[Guardião do Tempo] Lembrete antecipado suprimido para '{event.titulo}' porque o evento esta tentativo."
                    )
                    continue
                if event.inicio <= now:
                    self.store.mark_agenda_event_pre_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=now,
                    )
                    self._log_debug(
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
                if event.status != "firme":
                    self.store.mark_agenda_event_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=now,
                    )
                    self._log_debug(
                        f"[Guardião do Tempo] Lembrete no horario suprimido para '{event.titulo}' porque o evento esta tentativo."
                    )
                    continue
                if event.inicio < stale_cutoff:
                    self.store.mark_agenda_event_reminded(
                        user_id=self.settings.default_user_id,
                        event_id=event.id,
                        reminded_at=now,
                    )
                    self._log_debug(
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
                self._log_debug(f"[Guardião do Tempo] Falha no loop de lembretes: {str(exc)}")
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
        reminder_offset_minutes = self._extract_reminder_offset_minutes(normalized_text)
        action = self._detect_schedule_action(normalized_text, reminder_offset_minutes=reminder_offset_minutes)
        if not normalized_text:
            return AgendaProcessingResult(skipped_reason="empty_text")
        target_event = self._resolve_target_event(
            user_id=user_id,
            contact_name=contact_name,
            message_text=normalized_text,
        )
        if action == "cancel":
            if target_event is None:
                return AgendaProcessingResult(action="cancel", skipped_reason="cancel_target_not_found")
            deleted = self.store.delete_agenda_event(user_id=user_id, event_id=target_event.id)
            if not deleted:
                return AgendaProcessingResult(action="cancel", skipped_reason="cancel_apply_failed")
            self._log_debug(
                f"[Guardião do Tempo] Compromisso cancelado: '{target_event.titulo}' em {self._format_local(target_event.inicio)}."
            )
            return AgendaProcessingResult(
                detected=True,
                action="cancel",
                saved_event=target_event,
            )
        if not self._has_schedule_signal(normalized_text):
            if reminder_offset_minutes > 0:
                updated_event = self._apply_follow_up_reminder_instruction(
                    user_id=user_id,
                    contact_name=contact_name,
                    source_text=normalized_text,
                    reminder_offset_minutes=reminder_offset_minutes,
                )
                if updated_event is not None:
                    self._log_debug(
                        f"[Guardião do Tempo] Antecedência atualizada para '{updated_event.titulo}': {reminder_offset_minutes} minuto(s) antes em horário de Brasília."
                    )
                    return AgendaProcessingResult(
                        detected=True,
                        action="update_reminder",
                        saved_event=updated_event,
                        reminder_offset_minutes=reminder_offset_minutes,
                        updated_existing_event=True,
                    )
            if DATE_SIGNAL_REGEX.search(normalized_text):
                return self._clarification_result(
                    action="clarify",
                    reason="no_explicit_schedule_intent",
                    source_text=normalized_text,
                )
            return AgendaProcessingResult(action=action, skipped_reason="no_schedule_signal")

        self._log_debug(
            f"[Guardião do Tempo] Sinal temporal detectado em {source_label}: {normalized_text}"
        )

        try:
            extraction = await self.deepseek_service.extract_agenda_signal(
                message_text=normalized_text,
                reference_now=occurred_at.astimezone(DEFAULT_TIMEZONE),
            )
        except Exception as exc:
            self._log_debug(f"[Guardião do Tempo] Falha na extração estruturada: {str(exc)}")
            logger.warning("agenda_extraction_failed message_id=%s detail=%s", message_id, str(exc))
            return AgendaProcessingResult(skipped_reason="extract_failed")

        resolved_action = extraction.action if extraction.action != "none" else action
        if extraction.action == "clarify":
            return self._clarification_result(
                action="clarify",
                reason="model_requires_clarification",
                source_text=normalized_text,
            )

        if not extraction.has_schedule_signal:
            if DATE_SIGNAL_REGEX.search(normalized_text):
                return self._clarification_result(
                    action="clarify",
                    reason="time_without_schedule_commitment",
                    source_text=normalized_text,
                )
            return AgendaProcessingResult(action=resolved_action, skipped_reason="no_structured_schedule")

        if resolved_action in {"create", "reschedule"} and not extraction.data_inicio:
            return self._clarification_result(
                action="clarify",
                reason="missing_start_time",
                source_text=normalized_text,
            )

        resolved_status = self._resolve_status(extraction=extraction, source_text=normalized_text)
        inicio = self._normalize_datetime(extraction.data_inicio, reference=occurred_at)
        if inicio is None:
            self._log_debug("[Guardião do Tempo] Extração retornou data_inicio inválida.")
            return self._clarification_result(
                action="clarify",
                reason="invalid_start",
                source_text=normalized_text,
            )
        if inicio <= occurred_at.astimezone(UTC) - timedelta(minutes=5):
            return AgendaProcessingResult(action=resolved_action, skipped_reason="past_start")
        fim = self._normalize_datetime(extraction.data_fim, reference=occurred_at)
        if fim is None or fim <= inicio:
            duration_minutes = self._extract_duration_minutes(normalized_text)
            fim = inicio + timedelta(minutes=duration_minutes) if duration_minutes > 0 else inicio + DEFAULT_EVENT_DURATION

        if self._should_require_clarification(extraction=extraction, source_text=normalized_text, action=resolved_action):
            self._log_debug(
                "[Guardião do Tempo] Sinal de agenda bloqueado por ambiguidade ou baixa confianca."
            )
            return self._clarification_result(
                action="clarify",
                reason="low_confidence_or_ambiguous",
                source_text=normalized_text,
            )

        titulo = extraction.titulo.strip() if extraction.titulo.strip() else self._fallback_title(normalized_text)
        if self._is_generic_title(titulo):
            return self._clarification_result(
                action="clarify",
                reason="generic_title",
                source_text=normalized_text,
            )
        is_update = resolved_action == "reschedule" and target_event is not None and not NEW_EVENT_HINT_REGEX.search(normalized_text)
        if resolved_action in {"cancel", "reschedule", "update_reminder"} and target_event is None:
            return self._clarification_result(
                action="clarify",
                reason="target_event_not_resolved",
                source_text=normalized_text,
            )
        if is_update:
            titulo = self._resolve_updated_title(
                extracted_title=titulo,
                source_text=normalized_text,
                current_event=target_event,
            )
        self._log_debug(
            f"[Guardião do Tempo] Extração válida: '{titulo}' em {self._format_local(inicio)} ({resolved_status})."
        )

        conflicts = self.store.find_agenda_conflicts(
            user_id=user_id,
            inicio=inicio,
            fim=fim,
            exclude_message_id=target_event.message_id if is_update and target_event is not None else message_id,
            limit=1,
        )
        if is_update and target_event is not None:
            saved_event = self.store.update_agenda_event(
                user_id=user_id,
                event_id=target_event.id,
                titulo=titulo,
                inicio=inicio,
                fim=fim,
                status=resolved_status,
                contato_origem=contact_name,
                reminder_offset_minutes=(
                    reminder_offset_minutes if reminder_offset_minutes > 0 else target_event.reminder_offset_minutes
                ),
                reset_reminder=True,
            )
            if saved_event is None:
                return AgendaProcessingResult(action=resolved_action, skipped_reason="update_failed")
        else:
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
        self._log_debug(
            f"[Guardião do Tempo] Compromisso salvo: '{saved_event.titulo}' de {self._format_local(saved_event.inicio)} até {self._format_local(saved_event.fim)}."
        )
        if reminder_offset_minutes > 0:
            self._log_debug(
                f"[Guardião do Tempo] Lembrete antecipado configurado para {reminder_offset_minutes} minuto(s) antes, em horário de Brasília."
            )

        conflict_event = conflicts[0] if conflicts else None
        alert_sent = False
        if conflict_event is not None:
            self._log_debug(
                f"[Guardião do Tempo] Conflito detectado com '{conflict_event.titulo}' em {self._format_local(conflict_event.inicio)}."
            )
            if should_send_conflict_alert:
                alert_sent = await self._send_conflict_alert(new_event=saved_event, existing_event=conflict_event)

        return AgendaProcessingResult(
            detected=True,
            action="reschedule" if is_update else "create",
            saved_event=saved_event,
            conflict_event=conflict_event,
            alert_sent=alert_sent,
            reminder_offset_minutes=reminder_offset_minutes,
            updated_existing_event=is_update,
        )

    def _has_schedule_signal(self, text: str) -> bool:
        compact = " ".join((text or "").split()).strip()
        if not compact:
            return False
        has_date_signal = bool(DATE_SIGNAL_REGEX.search(compact))
        has_explicit_intent = bool(EXPLICIT_SCHEDULING_INTENT_REGEX.search(compact))
        return has_date_signal and has_explicit_intent

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

    def _detect_schedule_action(self, text: str, *, reminder_offset_minutes: int) -> str:
        compact = " ".join(text.split()).strip().lower()
        if not compact:
            return "none"
        if reminder_offset_minutes > 0 and not DATE_SIGNAL_REGEX.search(compact):
            return "update_reminder"
        if CANCEL_ACTION_REGEX.search(compact):
            return "cancel"
        if RESCHEDULE_ACTION_REGEX.search(compact):
            return "reschedule"
        return "create"

    def _should_require_clarification(
        self,
        *,
        extraction: DeepSeekAgendaExtractionResult,
        source_text: str,
        action: str,
    ) -> bool:
        confidence = int(extraction.confidence or 0)
        explicit_intent = bool(EXPLICIT_SCHEDULING_INTENT_REGEX.search(source_text))
        if action == "update_reminder" and confidence >= AGENDA_HIGH_CONFIDENCE_THRESHOLD and explicit_intent:
            return False
        if action in {"cancel", "reschedule"} and confidence >= AGENDA_HIGH_CONFIDENCE_THRESHOLD and explicit_intent:
            return False
        if extraction.is_explicit_user_intent and explicit_intent and confidence >= AGENDA_HIGH_CONFIDENCE_THRESHOLD:
            return False
        if confidence < AGENDA_CLARIFY_CONFIDENCE_THRESHOLD:
            return True
        if not extraction.is_explicit_user_intent:
            return True
        if DATE_SIGNAL_REGEX.search(source_text) and not explicit_intent and TIME_ONLY_CONTEXT_REGEX.search(source_text):
            return True
        extracted_title = (extraction.titulo or "").strip()
        return len(extracted_title) < 4 or self._is_generic_title(extracted_title)

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
        owner_target = await self._resolve_owner_chat_target()
        if not owner_target:
            self._log_debug("[Guardião do Tempo] Conflito detectado, mas o número conectado não foi localizado.")
            return False
        alternatives = self._find_available_time_slots(
            range_start=min(new_event.inicio, existing_event.inicio),
            range_end=max(new_event.fim, existing_event.fim),
            required_duration=max(
                new_event.fim - new_event.inicio,
                existing_event.fim - existing_event.inicio,
                timedelta(minutes=30),
            ),
            exclude_event_ids={new_event.id, existing_event.id},
            limit=3,
        )
        alternatives_text = ""
        if alternatives:
            alternatives_text = (
                "\nSugestões livres: "
                + "; ".join(self._format_time_slot_label(start_at, end_at) for start_at, end_at in alternatives)
            )
        message_text = (
            "⚠️ AuraCore: conflito de agenda identificado.\n"
            f"O compromisso '{new_event.titulo}' para {self._format_local(new_event.inicio)} "
            f"se sobrepõe a '{existing_event.titulo}', já marcado para este horário.\n"
            "Revise os horários e me diga se quer manter, ajustar ou descartar um deles."
            f"{alternatives_text}"
        )
        try:
            send_result = await self.agent_gateway.send_text_message(chat_jid=owner_target, message_text=message_text)
            await self._record_conflict_alert_message(
                owner_target=owner_target,
                message_text=message_text,
                sent_at=send_result.timestamp or datetime.now(UTC),
                whatsapp_message_id=send_result.message_id,
                new_event=new_event,
                existing_event=existing_event,
            )
            self._log_debug("[Guardião do Tempo] Alerta de conflito enviado pelo agente ao usuário.")
            return True
        except Exception as exc:
            self._log_debug(f"[Guardião do Tempo] Falha ao enviar alerta: {str(exc)}")
            logger.warning(
                "agenda_conflict_alert_failed message_id=%s conflict_message_id=%s detail=%s",
                new_event.message_id,
                existing_event.message_id,
                str(exc),
            )
            return False

    async def _record_conflict_alert_message(
        self,
        *,
        owner_target: str,
        message_text: str,
        sent_at: datetime,
        whatsapp_message_id: str | None,
        new_event: AgendaEventRecord,
        existing_event: AgendaEventRecord,
    ) -> None:
        owner_phone = self._normalize_chat_target(owner_target)
        if not owner_phone:
            return
        thread = self.store.get_or_create_whatsapp_agent_thread(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            chat_jid=owner_target,
            contact_name="Usuario",
            created_at=sent_at,
        )
        session, _ = self.store.resolve_whatsapp_agent_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=thread.contact_phone,
            chat_jid=thread.chat_jid,
            activity_at=sent_at,
            idle_timeout_minutes=60,
        )
        self.store.append_whatsapp_agent_message(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            direction="outbound",
            role="assistant",
            session_id=session.id,
            content=message_text,
            message_timestamp=sent_at,
            contact_phone=thread.contact_phone,
            chat_jid=thread.chat_jid,
            whatsapp_message_id=whatsapp_message_id,
            processing_status="sent",
            learning_status="not_applicable",
            send_status="sent" if whatsapp_message_id else None,
            metadata={
                "generated_by": "agenda_conflict_guardian",
                "agenda_conflict_pending": True,
                "agenda_conflict_new_event_id": new_event.id,
                "agenda_conflict_existing_event_id": existing_event.id,
                "agenda_conflict_sent_at": sent_at.isoformat(),
            },
            created_at=sent_at,
        )

    async def resolve_conflict_reply(
        self,
        *,
        user_id: UUID,
        contact_phone: str,
        message_id: str,
        message_text: str,
        occurred_at: datetime,
    ) -> AgendaConflictResolutionOutcome:
        pending_alert = self.store.find_latest_pending_agenda_conflict_alert(
            user_id=user_id,
            contact_phone=contact_phone,
        )
        if pending_alert is None:
            return AgendaConflictResolutionOutcome(handled=False, skipped_reason="no_pending_conflict")

        metadata = pending_alert.metadata if isinstance(pending_alert.metadata, dict) else {}
        new_event_id = self._optional_text(metadata.get("agenda_conflict_new_event_id"))
        existing_event_id = self._optional_text(metadata.get("agenda_conflict_existing_event_id"))
        if not new_event_id or not existing_event_id:
            self.store.update_whatsapp_agent_message(
                message_id=pending_alert.id,
                metadata={
                    **metadata,
                    "agenda_conflict_pending": False,
                    "agenda_conflict_resolved_at": occurred_at.astimezone(UTC).isoformat(),
                    "agenda_conflict_resolution": "clarify",
                    "agenda_conflict_resolution_message_id": message_id,
                    "agenda_conflict_resolution_text": message_text,
                    "agenda_conflict_resolution_explanation": "Missing conflict context in stored alert.",
                    "agenda_conflict_resolution_state": "missing_context",
                },
            )
            return AgendaConflictResolutionOutcome(
                handled=True,
                decision="clarify",
                assistant_reply=(
                    "Entendi a resposta, mas perdi o contexto do conflito anterior. "
                    "Pode me dizer qual compromisso eu devo manter e qual devo remover?"
                ),
                pending_alert_message_id=pending_alert.id,
                skipped_reason="missing_context",
            )

        new_event = self.store.get_agenda_event(user_id=user_id, event_id=new_event_id)
        existing_event = self.store.get_agenda_event(user_id=user_id, event_id=existing_event_id)
        if new_event is None or existing_event is None:
            self.store.update_whatsapp_agent_message(
                message_id=pending_alert.id,
                metadata={
                    **metadata,
                    "agenda_conflict_pending": False,
                    "agenda_conflict_resolved_at": occurred_at.astimezone(UTC).isoformat(),
                    "agenda_conflict_resolution": "clarify",
                    "agenda_conflict_resolution_message_id": message_id,
                    "agenda_conflict_resolution_text": message_text,
                    "agenda_conflict_resolution_explanation": "One of the conflict events is no longer available.",
                    "agenda_conflict_resolution_state": "stale_context",
                },
            )
            return AgendaConflictResolutionOutcome(
                handled=True,
                decision="clarify",
                assistant_reply=(
                    "Encontrei a resposta, mas um dos compromissos do conflito não está mais disponível. "
                    "Se quiser, posso revisar a agenda novamente."
                ),
                pending_alert_message_id=pending_alert.id,
                skipped_reason="stale_context",
            )

        conflict_context = self._build_conflict_context(
            new_event=new_event,
            existing_event=existing_event,
        )
        try:
            resolution = await self.deepseek_service.extract_agenda_conflict_resolution(
                message_text=message_text,
                conflict_context=conflict_context,
            )
        except Exception as exc:
            logger.warning("agenda_conflict_resolution_failed message_id=%s detail=%s", message_id, str(exc))
            resolution = DeepSeekAgendaConflictResolutionResult(
                decision="clarify",
                explanation="",
                confidence=0,
            )

        applied = False
        reply: str
        decision = resolution.decision

        if decision == "keep_new_cancel_existing":
            deleted = self.store.delete_agenda_event(user_id=user_id, event_id=existing_event.id)
            if deleted:
                applied = True
            updated_new = self.store.update_agenda_event(
                user_id=user_id,
                event_id=new_event.id,
                status="firme",
                reset_reminder=True,
            )
            if updated_new is not None:
                new_event = updated_new
                applied = True
            reply = (
                f"Perfeito. Vou manter '{new_event.titulo}' e remover '{existing_event.titulo}' da agenda."
                if applied
                else "Entendi a decisão, mas não consegui aplicar a alteração na agenda. Vou revisar o conflito."
            )
        elif decision == "keep_existing_cancel_new":
            deleted = self.store.delete_agenda_event(user_id=user_id, event_id=new_event.id)
            if deleted:
                applied = True
            updated_existing = self.store.update_agenda_event(
                user_id=user_id,
                event_id=existing_event.id,
                status="firme",
                reset_reminder=True,
            )
            if updated_existing is not None:
                existing_event = updated_existing
                applied = True
            reply = (
                f"Perfeito. Vou manter '{existing_event.titulo}' e remover '{new_event.titulo}' da agenda."
                if applied
                else "Entendi a decisão, mas não consegui aplicar a alteração na agenda. Vou revisar o conflito."
            )
        elif decision == "keep_both":
            updated_new = self.store.update_agenda_event(
                user_id=user_id,
                event_id=new_event.id,
                status="firme",
                reset_reminder=True,
            )
            if updated_new is not None:
                new_event = updated_new
                applied = True
            reply = (
                f"Entendido. Vou manter '{new_event.titulo}' e '{existing_event.titulo}' na agenda."
                if applied
                else "Entendi que você quer manter os dois compromissos, mas não consegui ajustar a agenda agora."
            )
        else:
            alternatives_suffix = ""
            if resolution.suggested_alternatives:
                alternatives_suffix = " Alternativas livres: " + "; ".join(resolution.suggested_alternatives[:3]) + "."
            reply = (
                "Ainda não ficou totalmente claro qual compromisso devo manter. "
                f"Hoje tenho '{new_event.titulo}' e '{existing_event.titulo}' em conflito. "
                f"Me diga qual deles devo preservar.{alternatives_suffix}"
            )

        metadata_update = {
            **metadata,
            "agenda_conflict_resolution": decision,
            "agenda_conflict_resolution_message_id": message_id,
            "agenda_conflict_resolution_text": message_text,
            "agenda_conflict_resolution_explanation": resolution.explanation,
        }
        if applied or decision != "clarify":
            metadata_update["agenda_conflict_pending"] = False
            metadata_update["agenda_conflict_resolved_at"] = occurred_at.astimezone(UTC).isoformat()
        else:
            metadata_update["agenda_conflict_pending"] = True
            metadata_update["agenda_conflict_last_clarify_at"] = occurred_at.astimezone(UTC).isoformat()

        self.store.update_whatsapp_agent_message(
            message_id=pending_alert.id,
            metadata=metadata_update,
        )

        return AgendaConflictResolutionOutcome(
            handled=True,
            applied=applied,
            decision=decision,
            assistant_reply=reply,
            pending_alert_message_id=pending_alert.id,
            new_event=new_event,
            existing_event=existing_event,
        )

    def _build_conflict_context(self, *, new_event: AgendaEventRecord, existing_event: AgendaEventRecord) -> str:
        alternatives = self._find_available_time_slots(
            range_start=min(new_event.inicio, existing_event.inicio),
            range_end=max(new_event.fim, existing_event.fim),
            required_duration=max(
                new_event.fim - new_event.inicio,
                existing_event.fim - existing_event.inicio,
                timedelta(minutes=30),
            ),
            exclude_event_ids={new_event.id, existing_event.id},
            limit=3,
        )
        alternatives_block = ""
        if alternatives:
            alternatives_block = "\n\nHorarios alternativos livres:\n" + "\n".join(
                f"- {self._format_time_slot_label(start_at, end_at)}"
                for start_at, end_at in alternatives
            )
        return (
            "Novo compromisso:\n"
            f"- titulo: {new_event.titulo}\n"
            f"- inicio: {self._format_local(new_event.inicio)}\n"
            f"- fim: {self._format_local(new_event.fim)}\n"
            f"- status: {new_event.status}\n\n"
            "Compromisso em conflito:\n"
            f"- titulo: {existing_event.titulo}\n"
            f"- inicio: {self._format_local(existing_event.inicio)}\n"
            f"- fim: {self._format_local(existing_event.fim)}\n"
            f"- status: {existing_event.status}"
            f"{alternatives_block}"
        )

    def _find_available_time_slots(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        required_duration: timedelta,
        exclude_event_ids: set[str] | None = None,
        limit: int = 3,
    ) -> list[tuple[datetime, datetime]]:
        resolved_duration = max(required_duration, timedelta(minutes=30))
        exclude_ids = exclude_event_ids or set()
        start_local = range_start.astimezone(DEFAULT_TIMEZONE).replace(hour=8, minute=0, second=0, microsecond=0)
        end_local = (range_end.astimezone(DEFAULT_TIMEZONE) + timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)
        events = [
            event
            for event in self.store.list_agenda_events(
                user_id=self.settings.default_user_id,
                limit=120,
                starts_after=start_local.astimezone(UTC),
            )
            if event.id not in exclude_ids and event.inicio < end_local.astimezone(UTC)
        ]

        slots: list[tuple[datetime, datetime]] = []
        cursor_day = start_local.date()
        end_day = end_local.date()
        while cursor_day <= end_day and len(slots) < max(1, limit):
            day_start_local = datetime.combine(cursor_day, datetime.min.time(), tzinfo=DEFAULT_TIMEZONE).replace(hour=8)
            day_end_local = datetime.combine(cursor_day, datetime.min.time(), tzinfo=DEFAULT_TIMEZONE).replace(hour=21)
            day_events = sorted(
                [
                    event
                    for event in events
                    if event.inicio.astimezone(DEFAULT_TIMEZONE) < day_end_local
                    and event.fim.astimezone(DEFAULT_TIMEZONE) > day_start_local
                ],
                key=lambda event: event.inicio,
            )
            cursor = day_start_local
            for event in day_events:
                event_start = max(event.inicio.astimezone(DEFAULT_TIMEZONE), day_start_local)
                event_end = min(event.fim.astimezone(DEFAULT_TIMEZONE), day_end_local)
                if event_start - cursor >= resolved_duration:
                    slots.append((cursor.astimezone(UTC), (cursor + resolved_duration).astimezone(UTC)))
                    if len(slots) >= max(1, limit):
                        return slots
                if event_end > cursor:
                    cursor = event_end
            if day_end_local - cursor >= resolved_duration and len(slots) < max(1, limit):
                slots.append((cursor.astimezone(UTC), (cursor + resolved_duration).astimezone(UTC)))
            cursor_day += timedelta(days=1)
        return slots[: max(1, limit)]

    def _format_time_slot_label(self, start_at: datetime, end_at: datetime) -> str:
        local_start = start_at.astimezone(DEFAULT_TIMEZONE)
        local_end = end_at.astimezone(DEFAULT_TIMEZONE)
        return f"{local_start.strftime('%d/%m %H:%M')}-{local_end.strftime('%H:%M')}"

    async def _send_due_reminder(self, *, event: AgendaEventRecord, phase: str) -> bool:
        owner_target = await self._resolve_owner_chat_target()
        if not owner_target:
            self._log_debug(
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
            self._log_debug(
                f"[Guardião do Tempo] Lembrete {'antecipado' if phase == 'pre' else 'no horário'} enviado para '{event.titulo}'."
            )
            return True
        except Exception as send_exc:
            self._log_debug(
                f"[Guardião do Tempo] Falha ao enviar lembrete de '{event.titulo}': {str(send_exc)}"
            )
            logger.warning(
                "agenda_due_reminder_failed event_id=%s detail=%s",
                event.id,
                str(send_exc),
            )
            return False

    async def _resolve_owner_chat_target(self) -> str | None:
        try:
            observer_target = self._normalize_chat_target(
                (await self.observer_gateway.get_observer_status(refresh_qr=False)).owner_number
            )
        except Exception:
            observer_target = None
        if observer_target:
            logger.info(
                "agenda_owner_target_resolved user_id=%s source=observer_status",
                self.settings.default_user_id,
            )
            return observer_target

        observer_session_target = self._normalize_chat_target(
            self.store.get_whatsapp_session_owner_phone(session_id=f"{self.settings.default_user_id}:observer")
        )
        if observer_session_target:
            logger.info(
                "agenda_owner_target_resolved user_id=%s source=observer_session",
                self.settings.default_user_id,
            )
            return observer_session_target
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

    def _log_debug(self, content: str) -> None:
        logger.debug(content)

    def _fallback_title(self, text: str) -> str:
        compact = " ".join(text.split()).strip()
        return compact[:120] if compact else "Compromisso"

    def _extract_duration_minutes(self, text: str) -> int:
        compact = " ".join(text.split()).strip().lower()
        if not compact:
            return 0
        for pattern in DURATION_REGEXES:
            match = pattern.search(compact)
            if not match:
                continue
            amount = self._parse_reminder_amount(match.group("amount"))
            unit = (match.group("unit") or "").strip().lower()
            if amount <= 0:
                continue
            if unit.startswith("min"):
                return min(amount, 1440)
            if unit.startswith("h"):
                return min(amount * 60, 1440)
        return 0

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

    def _apply_follow_up_reminder_instruction(
        self,
        *,
        user_id: UUID,
        contact_name: str,
        source_text: str,
        reminder_offset_minutes: int,
    ) -> AgendaEventRecord | None:
        target_event = self._resolve_target_event(
            user_id=user_id,
            contact_name=contact_name,
            message_text=source_text,
        )
        if target_event is None or self._score_event_match(message_tokens=self._extract_title_tokens(source_text), event=target_event) <= 0:
            return None
        return self.store.update_agenda_event(
            user_id=user_id,
            event_id=target_event.id,
            reminder_offset_minutes=reminder_offset_minutes,
            reset_reminder=True,
        )

    def _resolve_target_event(
        self,
        *,
        user_id: UUID,
        contact_name: str,
        message_text: str,
    ) -> AgendaEventRecord | None:
        latest = self.store.find_latest_upcoming_agenda_event_for_contact(
            user_id=user_id,
            contato_origem=contact_name,
            now=datetime.now(UTC),
        )
        if latest is None:
            return None
        message_tokens = self._extract_title_tokens(message_text)
        if not message_tokens:
            return latest
        candidate_events = [
            event
            for event in self.store.list_agenda_events(user_id=user_id, limit=120, starts_after=datetime.now(UTC))
            if (event.contato_origem or "").strip().casefold() == (contact_name or "").strip().casefold()
        ]
        best_event = latest
        best_score = self._score_event_match(message_tokens=message_tokens, event=latest)
        tie = False
        for event in candidate_events:
            score = self._score_event_match(message_tokens=message_tokens, event=event)
            if score > best_score:
                best_event = event
                best_score = score
                tie = False
            elif score > 0 and score == best_score and event.id != best_event.id:
                tie = True
        if best_score <= 0 or tie:
            return None
        return best_event

    def _resolve_updated_title(
        self,
        *,
        extracted_title: str,
        source_text: str,
        current_event: AgendaEventRecord,
    ) -> str:
        compact_title = " ".join((extracted_title or "").split()).strip()
        if not compact_title:
            return current_event.titulo
        if compact_title.casefold() == current_event.titulo.strip().casefold():
            return current_event.titulo
        message_tokens = self._extract_title_tokens(source_text)
        title_tokens = self._extract_title_tokens(compact_title)
        if not title_tokens:
            return current_event.titulo
        if title_tokens.issubset(message_tokens) and not EVENT_KEYWORD_REGEX.search(compact_title):
            return current_event.titulo
        return compact_title

    def _extract_title_tokens(self, text: str) -> set[str]:
        tokens = {
            token.casefold()
            for token in TITLE_TOKEN_REGEX.findall((text or "").strip())
            if token.casefold() not in TITLE_STOPWORDS
        }
        return tokens

    def _score_event_match(self, *, message_tokens: set[str], event: AgendaEventRecord) -> int:
        title_tokens = self._extract_title_tokens(event.titulo)
        if not title_tokens or not message_tokens:
            return 0
        overlap = title_tokens & message_tokens
        score = len(overlap) * 10
        time_match = re.search(r"\b(?:[àa]s?\s*)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\b", " ".join(message_tokens))
        if time_match:
            hour = int(time_match.group("hour"))
            minute = int(time_match.group("minute") or 0)
            localized = event.inicio.astimezone(DEFAULT_TIMEZONE)
            if localized.hour == hour and localized.minute == minute:
                score += 6
        return score

    def _is_generic_title(self, title: str) -> bool:
        normalized = " ".join((title or "").split()).strip().casefold()
        if not normalized:
            return True
        if normalized in GENERIC_TITLES:
            return True
        tokens = self._extract_title_tokens(normalized)
        return len(tokens) <= 1 and normalized in {"consulta", "reuniao", "reunião", "aula", "call"}

    def _clarification_result(self, *, action: str, reason: str, source_text: str) -> AgendaProcessingResult:
        return AgendaProcessingResult(
            detected=True,
            action=action,
            clarification_needed=True,
            clarification_reply=self._build_clarification_reply(source_text=source_text),
            skipped_reason=reason,
        )

    def _build_clarification_reply(self, *, source_text: str) -> str:
        if DATE_SIGNAL_REGEX.search(source_text):
            return (
                "Vi um horário possível nessa mensagem, mas ainda não ficou claro se você quer que eu salve isso na agenda. "
                "Se quiser, me confirme com algo como: 'marque na agenda amanhã às 19:15' e, se puder, diga também o título."
            )
        return (
            "Entendi que isso pode envolver agenda, mas ainda faltam detalhes para eu salvar com segurança. "
            "Me diga o compromisso, a data e o horário de forma explícita."
        )

    def format_reminder_rule(self, event: AgendaEventRecord) -> str:
        if event.status != "firme":
            return "Sem lembrete automatico para evento tentativo"
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
