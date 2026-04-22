from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from difflib import SequenceMatcher
import hashlib
import logging
import re
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.deepseek_service import DeepSeekService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.banco_de_dados_local_store import (
    ImportantMessageRecord,
    ProjectMemoryRecord,
    ProactiveCandidateRecord,
    ProactiveDeliveryLogRecord,
    ProactivePreferencesRecord,
    BancoDeDadosLocalStore,
    WhatsAppAgentContactMemoryRecord,
    WhatsAppAgentThreadRecord,
)

DEFAULT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
PROACTIVE_LOOP_INTERVAL_SECONDS = 45
RECENT_REPLY_WINDOW_HOURS = 36
RECENT_PROJECT_NUDGE_HOURS = 8
RECENT_OWNER_ACTIVITY_SUPPRESSION_MINUTES = 18
IMPORTANT_MESSAGE_CANDIDATE_HOURS = 96
PROJECT_STALE_NUDGE_HOURS = 8
RECENT_OWNER_THREAD_LOOKBACK_DAYS = 14
UNANSWERED_PROACTIVE_WINDOW_MINUTES = 120
RECENT_PROACTIVE_EXAMPLES_LIMIT = 5
RECENT_PROMPT_EXAMPLES_LIMIT = 3
MESSAGE_SIMILARITY_THRESHOLD = 0.72
ORGANIC_JITTER_WINDOWS: dict[str, tuple[int, int]] = {
    "followup": (3, 12),
    "project_nudge": (8, 25),
    "routine": (12, 30),
    "morning_digest": (10, 25),
    "night_digest": (10, 25),
}
FOLLOWUP_KEYWORDS = ("responder", "mandar", "enviar", "ver", "fazer", "cobrar", "retornar", "ajustar")
FUTURE_MARKERS = ("amanha", "amanhã", "mais tarde", "depois", "hoje", "semana", "mais tarde", "na volta")
ROUTINE_PATTERNS = (
    ("cansado", "Você pareceu mais cansado agora."),
    ("exausto", "Você deu sinal de exaustão agora."),
    ("sobrecarregado", "Você sinalizou sobrecarga."),
    ("sobrecarregada", "Você sinalizou sobrecarga."),
    ("sem foco", "Você comentou que está sem foco."),
    ("ansioso", "Você pareceu mais pressionado agora."),
    ("ansiosa", "Você pareceu mais pressionada agora."),
    ("estressado", "Você pareceu estressado agora."),
    ("estressada", "Você pareceu estressada agora."),
    ("muita coisa", "Sua carga do momento parece alta."),
    ("corrido", "Seu ritmo do momento parece bem corrido."),
)
AFFIRMATIVE_REGEX = re.compile(r"\b(?:sim|pode|quero|bora|ok|beleza|manda|lembra|lembre|fechado)\b", re.IGNORECASE)
NEGATIVE_REGEX = re.compile(r"\b(?:nao|não|deixa|ignora|dispensa|cancela|pare|agora nao|agora não)\b", re.IGNORECASE)
DONE_REGEX = re.compile(r"\b(?:ja fiz|já fiz|resolvi|conclui|concluí|feito|finalizei|terminei)\b", re.IGNORECASE)
REMINDER_REQUEST_REGEX = re.compile(r"(?:me\s+lembra|me\s+lembre)\s+(?:de\s+)?(?P<task>.+)", re.IGNORECASE)
RELATIVE_DELAY_REGEX = re.compile(
    r"\bdaqui\s+a?\s*(?P<amount>\d{1,3}|uma|um|meia)\s*(?P<unit>min(?:uto)?s?|h(?:ora)?s?|dia?s?)\b",
    re.IGNORECASE,
)
logger = logging.getLogger("auracore.proactive_assistant")


@dataclass(slots=True)
class ProactiveReplyOutcome:
    handled: bool = False
    assistant_reply: str | None = None
    candidate: ProactiveCandidateRecord | None = None


@dataclass(slots=True)
class OwnerProactiveContext:
    memory: WhatsAppAgentContactMemoryRecord | None
    recent_inbound_lines: list[str]
    recent_mood_signals: list[str]
    recent_implied_tasks: list[str]
    recent_style_hints: list[str]


@dataclass(slots=True)
class OwnerVoiceProfile:
    guidance: str
    prefers_direct: bool
    prefers_playful: bool
    prefers_formal: bool


class ProactiveAssistantService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: BancoDeDadosLocalStore,
        deepseek_service: DeepSeekService,
        observer_gateway: ObserverGatewayService,
        agent_gateway: WhatsAppAgentGatewayService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service
        self.observer_gateway = observer_gateway
        self.agent_gateway = agent_gateway
        self._loop_task: asyncio.Task[None] | None = None
        self._tick_lock = asyncio.Lock()

    def warm_start(self) -> None:
        existing = self._loop_task
        if existing is not None and not existing.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("proactive_assistant_loop_not_started user_id=%s reason=no_running_loop", self.settings.default_user_id)
            return
        self._loop_task = loop.create_task(
            self._run_loop(),
            name=f"proactive-assistant-{self.settings.default_user_id}",
        )

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("proactive_assistant_tick_failed")
            await asyncio.sleep(PROACTIVE_LOOP_INTERVAL_SECONDS)

    async def tick(self) -> None:
        async with self._tick_lock:
            prefs = self.store.get_proactive_preferences(self.settings.default_user_id)
            if not prefs.enabled:
                return
            now = datetime.now(UTC)
            self._seed_important_followups_if_needed(prefs=prefs, now=now)
            await self._seed_project_nudge_if_needed(prefs=prefs, now=now)
            await self._send_daily_digests_if_due(prefs=prefs, now=now)
            await self._send_due_candidates(prefs=prefs, now=now)

    def list_candidates(self, *, limit: int = 20, statuses: list[str] | None = None) -> list[ProactiveCandidateRecord]:
        return self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=limit,
            statuses=statuses,
        )

    def list_deliveries(self, *, limit: int = 20):
        return self.store.list_recent_proactive_deliveries(user_id=self.settings.default_user_id, limit=limit)

    def get_preferences(self) -> ProactivePreferencesRecord:
        return self.store.get_proactive_preferences(self.settings.default_user_id)

    def update_preferences(self, **kwargs: Any) -> ProactivePreferencesRecord:
        return self.store.update_proactive_preferences(user_id=self.settings.default_user_id, **kwargs)

    def update_candidate_status(self, *, candidate_id: str, status: str) -> ProactiveCandidateRecord | None:
        updates: dict[str, Any] = {"status": status}
        if status in {"dismissed", "done", "expired"}:
            updates["cooldown_until"] = datetime.now(UTC) + timedelta(days=7)
        return self.store.update_proactive_candidate(candidate_id=candidate_id, **updates)

    def get_recent_reply_candidate(
        self,
        *,
        contact_phone: str,
        now: datetime,
    ) -> ProactiveCandidateRecord | None:
        normalized_phone = self.store.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return None
        return self._find_reply_candidate(contact_phone=normalized_phone, now=now)

    def build_recent_reply_priority_context(
        self,
        *,
        contact_phone: str,
        now: datetime,
    ) -> str:
        candidate = self.get_recent_reply_candidate(contact_phone=contact_phone, now=now)
        if candidate is None:
            return ""
        return self._build_candidate_priority_context(candidate)

    async def capture_owner_message(
        self,
        *,
        thread_id: str,
        contact_phone: str,
        chat_jid: str | None,
        source_message_id: str,
        message_text: str,
        occurred_at: datetime,
        learning_signals: dict[str, Any] | None = None,
    ) -> None:
        prefs = self.store.get_proactive_preferences(self.settings.default_user_id)
        if not prefs.enabled:
            return

        normalized_phone = self.store.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return

        active_candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=80,
            statuses=["suggested", "sent", "confirmed"],
            contact_phone=normalized_phone,
        )
        created_any = False

        followup = self._detect_followup_candidate(
            message_text=message_text,
            occurred_at=occurred_at,
            thread_id=thread_id,
            contact_phone=normalized_phone,
            chat_jid=chat_jid,
            source_message_id=source_message_id,
        )
        if followup is not None and prefs.followups_enabled:
            self._create_or_refresh_candidate(active_candidates=active_candidates, candidate_data=followup)
            created_any = True

        routine = self._detect_routine_candidate(
            message_text=message_text,
            occurred_at=occurred_at,
            thread_id=thread_id,
            contact_phone=normalized_phone,
            chat_jid=chat_jid,
            source_message_id=source_message_id,
            learning_signals=learning_signals or {},
        )
        if routine is not None and prefs.routine_enabled:
            self._create_or_refresh_candidate(active_candidates=active_candidates, candidate_data=routine)
            created_any = True

        if created_any:
            logger.info(
                "proactive_assistant_candidates_updated user_id=%s contact_phone=%s source_message_id=%s",
                self.settings.default_user_id,
                normalized_phone,
                source_message_id,
            )

    def handle_owner_reply(
        self,
        *,
        contact_phone: str,
        message_text: str,
        occurred_at: datetime,
    ) -> ProactiveReplyOutcome:
        normalized_phone = self.store.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return ProactiveReplyOutcome()

        candidate = self._find_reply_candidate(contact_phone=normalized_phone, now=occurred_at)
        if candidate is None:
            return ProactiveReplyOutcome()
        if len(" ".join(message_text.split())) > 160:
            return ProactiveReplyOutcome()

        reply_kind = self._classify_reply(message_text)
        if reply_kind == "none":
            return ProactiveReplyOutcome()

        if reply_kind == "done":
            updated = self.store.update_proactive_candidate(
                candidate_id=candidate.id,
                status="done",
                cooldown_until=occurred_at + timedelta(days=14),
            )
            return ProactiveReplyOutcome(
                handled=True,
                assistant_reply="Boa. Marquei isso como resolvido e tiro esse assunto do radar por enquanto.",
                candidate=updated or candidate,
            )

        if reply_kind == "dismiss":
            updated = self.store.update_proactive_candidate(
                candidate_id=candidate.id,
                status="dismissed",
                cooldown_until=occurred_at + timedelta(days=3),
            )
            return ProactiveReplyOutcome(
                handled=True,
                assistant_reply="Fechado. Não vou insistir nisso agora.",
                candidate=updated or candidate,
            )

        next_due = occurred_at + (timedelta(hours=6) if candidate.category != "routine" else timedelta(days=1))
        next_status = "confirmed" if candidate.category in {"followup", "project_nudge"} else "done"
        updated = self.store.update_proactive_candidate(
            candidate_id=candidate.id,
            status=next_status,
            due_at=next_due if next_status == "confirmed" else None,
            cooldown_until=occurred_at + timedelta(hours=3),
        )
        if candidate.category == "routine":
            reply_text = "Fechado. Vou tratar isso como um ajuste pontual e não vou transformar em cobrança."
        else:
            reply_text = (
                "Perfeito. Vou manter isso no radar e, se continuar aberto, te cutuco de novo no momento certo."
            )
        return ProactiveReplyOutcome(
            handled=True,
            assistant_reply=reply_text,
            candidate=updated or candidate,
        )

    def _classify_reply(self, message_text: str) -> str:
        normalized = " ".join(message_text.split()).strip().lower()
        if not normalized:
            return "none"
        if DONE_REGEX.search(normalized):
            return "done"
        if NEGATIVE_REGEX.search(normalized):
            return "dismiss"
        if AFFIRMATIVE_REGEX.search(normalized):
            return "confirm"
        return "none"

    def _find_reply_candidate(self, *, contact_phone: str, now: datetime) -> ProactiveCandidateRecord | None:
        candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=20,
            statuses=["sent", "confirmed"],
            contact_phone=contact_phone,
        )
        window_start = now - timedelta(hours=RECENT_REPLY_WINDOW_HOURS)
        for candidate in candidates:
            pivot = candidate.last_nudged_at or candidate.updated_at
            if pivot >= window_start:
                return candidate
        return None

    def _detect_followup_candidate(
        self,
        *,
        message_text: str,
        occurred_at: datetime,
        thread_id: str,
        contact_phone: str,
        chat_jid: str | None,
        source_message_id: str,
    ) -> dict[str, Any] | None:
        normalized = " ".join(message_text.lower().split()).strip()
        if len(normalized) < 12:
            return None

        task_text: str | None = None
        confidence = 68
        priority = 62
        reminder_match = REMINDER_REQUEST_REGEX.search(message_text)
        if reminder_match:
            task_text = reminder_match.group("task").strip(" .,:;")
            confidence = 94
            priority = 82
        else:
            has_keyword = any(keyword in normalized for keyword in FOLLOWUP_KEYWORDS)
            has_future_marker = any(marker in normalized for marker in FUTURE_MARKERS)
            has_need = any(marker in normalized for marker in ("preciso", "tenho que", "nao esquecer", "não esquecer"))
            if not ((has_keyword and has_future_marker) or has_need):
                return None
            task_text = self._extract_followup_task(message_text)
            if has_need:
                confidence += 8
                priority += 10

        if not task_text:
            return None

        due_at = self._resolve_followup_due_at(message_text=normalized, occurred_at=occurred_at)
        if "deadline" in normalized or "prazo" in normalized or "urgente" in normalized:
            confidence = max(confidence, 86)
            priority = max(priority, 82)
        title = f"Pendente sugerida: {task_text[:88]}".strip()
        dedupe_key = f"followup:{self._dedupe_token(task_text)}"
        return {
            "category": "followup",
            "status": "suggested",
            "source_message_id": source_message_id,
            "source_kind": "owner_message",
            "thread_id": thread_id,
            "contact_phone": contact_phone,
            "chat_jid": chat_jid,
            "title": title,
            "summary": f"Você mesmo levantou isso como algo que precisará ser retomado: {task_text[:180]}",
            "confidence": confidence,
            "priority": priority,
            "due_at": due_at,
            "cooldown_until": occurred_at + timedelta(minutes=30),
            "last_nudged_at": None,
            "payload_json": {
                "dedupe_key": dedupe_key,
                "task_text": task_text,
                "source_excerpt": " ".join(message_text.split())[:220],
            },
        }

    def _detect_routine_candidate(
        self,
        *,
        message_text: str,
        occurred_at: datetime,
        thread_id: str,
        contact_phone: str,
        chat_jid: str | None,
        source_message_id: str,
        learning_signals: dict[str, Any],
    ) -> dict[str, Any] | None:
        normalized = " ".join(message_text.lower().split()).strip()
        if len(normalized) < 12:
            return None

        matched_reason: str | None = None
        for pattern, reason_text in ROUTINE_PATTERNS:
            if pattern in normalized:
                matched_reason = reason_text
                break

        if matched_reason is None:
            mood_signals = [str(item).strip().lower() for item in (learning_signals.get("mood_signals") or []) if str(item).strip()]
            for signal in mood_signals:
                if any(marker in signal for marker in ("apressado", "frustrado", "cansado", "sobrecarregado", "ansioso")):
                    matched_reason = f"Sinal recente detectado: {signal}"
                    break

        if matched_reason is None:
            return None

        suggestion = "Vale segurar 15 min para reorganizar o resto do dia ou cortar uma frente agora."
        if "sem foco" in normalized:
            suggestion = "Vale fechar um bloco curto de foco agora e empurrar o resto."
        elif "cans" in normalized or "exaust" in normalized:
            suggestion = "Vale fazer uma pausa curta antes de tentar empilhar mais coisa."

        return {
            "category": "routine",
            "status": "suggested",
            "source_message_id": source_message_id,
            "source_kind": "owner_message",
            "thread_id": thread_id,
            "contact_phone": contact_phone,
            "chat_jid": chat_jid,
            "title": "Ajuste leve de rotina sugerido",
            "summary": matched_reason,
            "confidence": 70,
            "priority": 56,
            "due_at": occurred_at + timedelta(minutes=50),
            "cooldown_until": occurred_at + timedelta(hours=6),
            "last_nudged_at": None,
            "payload_json": {
                "dedupe_key": f"routine:{self._dedupe_token(matched_reason)}",
                "suggestion": suggestion,
            },
        }

    async def _seed_project_nudge_if_needed(self, *, prefs: ProactivePreferencesRecord, now: datetime) -> None:
        if not prefs.projects_enabled:
            return
        active_candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=40,
            statuses=["suggested", "sent", "confirmed"],
            categories=["project_nudge"],
        )
        if active_candidates:
            return
        recent_deliveries = self.store.list_recent_proactive_deliveries(user_id=self.settings.default_user_id, limit=30)
        for delivery in recent_deliveries:
            if delivery.category == "project_nudge" and delivery.created_at >= now - timedelta(hours=RECENT_PROJECT_NUDGE_HOURS):
                return

        projects = [
            project
            for project in self.store.list_project_memories(self.settings.default_user_id, limit=8)
            if project.project_name.strip() and project.completion_source != "manual"
        ]
        if not projects:
            return
        important_messages = self.store.list_important_messages(self.settings.default_user_id, limit=8)
        selected_project = self._select_project_for_nudge(
            projects=projects,
            important_messages=important_messages,
            now=now,
        )
        if selected_project is None:
            return
        project, related_signals, project_score = selected_project
        next_step = project.next_steps[0] if project.next_steps else ""
        summary = next_step or project.summary or project.what_is_being_built or "Projeto ativo sem próximo passo manual definido."
        suggested_actions = await self._generate_project_action_hints(project=project)
        signal_reason = self._describe_project_signal(project=project, related_signals=related_signals)
        self.store.create_proactive_candidate(
            user_id=self.settings.default_user_id,
            category="project_nudge",
            status="suggested",
            source_message_id=None,
            source_kind="project_memory",
            thread_id=None,
            contact_phone=self._resolve_owner_phone(),
            chat_jid=self._resolve_recent_owner_chat_target(now=now),
            title=f"Revisar projeto: {project.project_name[:72]}",
            summary=summary[:220] if not signal_reason else f"{summary[:140]} | {signal_reason[:72]}",
            confidence=max(74, min(96, 64 + round(project_score * 0.28))),
            priority=max(64, min(94, 58 + round(project_score * 0.34))),
            due_at=now + timedelta(minutes=15 if related_signals else 25),
            cooldown_until=now + timedelta(minutes=15),
            last_nudged_at=None,
            payload_json={
                "dedupe_key": f"project:{self._dedupe_token(project.project_name)}",
                "project_key": project.project_key,
                "project_name": project.project_name,
                "next_step": next_step,
                "suggested_actions": suggested_actions,
                "project_reason": signal_reason,
                "recent_signal": bool(related_signals),
            },
            created_at=now,
            updated_at=now,
        )

    async def _send_daily_digests_if_due(self, *, prefs: ProactivePreferencesRecord, now: datetime) -> None:
        local_now = now.astimezone(DEFAULT_TIMEZONE)
        if self._is_quiet_time(local_now, prefs):
            return
        digest_state = self.store.get_proactive_digest_state(user_id=self.settings.default_user_id)

        if prefs.morning_digest_enabled and self._digest_is_due(local_now=local_now, last_sent_at=digest_state.last_morning_digest_at, target_time=prefs.morning_digest_time):
            digest_payload, signature = self._build_morning_digest(now=now)
            if digest_payload and signature != digest_state.last_morning_digest_signature:
                sent = await self._attempt_digest_delivery(
                    category="morning_digest",
                    digest_payload=digest_payload,
                    signature=signature,
                    prefs=prefs,
                    now=now,
                    score=84,
                    reason_text="Resumo curto da manha.",
                    scheduled_time_text=prefs.morning_digest_time,
                )
                if sent:
                    self.store.update_proactive_digest_state(
                        user_id=self.settings.default_user_id,
                        last_morning_digest_at=now,
                        last_morning_digest_signature=signature,
                    )

        if prefs.night_digest_enabled and self._digest_is_due(local_now=local_now, last_sent_at=digest_state.last_night_digest_at, target_time=prefs.night_digest_time):
            digest_payload, signature = self._build_night_digest(now=now)
            if digest_payload and signature != digest_state.last_night_digest_signature:
                sent = await self._attempt_digest_delivery(
                    category="night_digest",
                    digest_payload=digest_payload,
                    signature=signature,
                    prefs=prefs,
                    now=now,
                    score=80,
                    reason_text="Fechamento curto do dia.",
                    scheduled_time_text=prefs.night_digest_time,
                )
                if sent:
                    self.store.update_proactive_digest_state(
                        user_id=self.settings.default_user_id,
                        last_night_digest_at=now,
                        last_night_digest_signature=signature,
                    )

    async def _send_due_candidates(self, *, prefs: ProactivePreferencesRecord, now: datetime) -> None:
        if not prefs.enabled:
            return
        local_now = now.astimezone(DEFAULT_TIMEZONE)
        if self._is_quiet_time(local_now, prefs):
            return
        if self._daily_send_budget_exhausted(prefs=prefs, now=now):
            return
        moment_state = self._detect_moment_state(now=now)
        recent_owner_inbound = self._recent_owner_inbound_activity(now=now)
        last_sent_delivery = self._last_sent_delivery()
        logger.info(
            "proactive_moment_state user_id=%s moment_state=%s recent_owner_inbound=%s",
            self.settings.default_user_id,
            moment_state,
            recent_owner_inbound,
        )

        best_candidate: ProactiveCandidateRecord | None = None
        best_score = -1
        best_due_at: datetime | None = None

        for candidate in self.store.list_due_proactive_candidates(
            user_id=self.settings.default_user_id,
            due_before=now,
            limit=12,
        ):
            if not self._candidate_enabled(candidate=candidate, prefs=prefs):
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="suppressed",
                    score=0,
                    reason_code="category_disabled",
                    reason_text="Categoria desabilitada nas preferências.",
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=now + timedelta(hours=8),
                )
                continue

            suppression = self._moment_suppression(candidate=candidate, moment_state=moment_state, now=now)
            if suppression is not None:
                reason_code, reason_text, cooldown_until = suppression
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="skipped",
                    score=0,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=cooldown_until,
                )
                continue

            jitter_suppression = self._organic_jitter_suppression(
                category=candidate.category,
                stable_key=candidate.id,
                due_at=candidate.due_at or now,
                now=now,
            )
            if jitter_suppression is not None:
                reason_code, reason_text, cooldown_until = jitter_suppression
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="skipped",
                    score=0,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=cooldown_until,
                )
                continue

            can_bypass_soft_holds = self._candidate_can_bypass_soft_holds(candidate)
            recent_activity_suppression = self._recent_owner_activity_suppression(
                category=candidate.category,
                now=now,
                recent_owner_inbound=recent_owner_inbound,
                can_bypass=can_bypass_soft_holds,
            )
            if recent_activity_suppression is not None:
                reason_code, reason_text, cooldown_until = recent_activity_suppression
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="skipped",
                    score=0,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=cooldown_until,
                )
                continue

            unanswered_nudge_suppression = self._unanswered_previous_nudge_suppression(
                category=candidate.category,
                now=now,
                last_sent_delivery=last_sent_delivery,
                can_bypass=can_bypass_soft_holds,
            )
            if unanswered_nudge_suppression is not None:
                reason_code, reason_text, cooldown_until = unanswered_nudge_suppression
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="skipped",
                    score=0,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=cooldown_until,
                )
                continue

            interval_suppression = self._min_interval_suppression(
                category=candidate.category,
                prefs=prefs,
                now=now,
                last_sent_delivery=last_sent_delivery,
                can_bypass=can_bypass_soft_holds,
            )
            if interval_suppression is not None:
                reason_code, reason_text, cooldown_until = interval_suppression
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="skipped",
                    score=0,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=cooldown_until,
                )
                continue

            score = self._score_candidate(
                candidate=candidate,
                now=now,
                moment_state=moment_state,
                prefs=prefs,
            )
            minimum_score = self._minimum_candidate_score(candidate=candidate, prefs=prefs)
            if score < minimum_score:
                self.store.create_proactive_delivery_log(
                    user_id=self.settings.default_user_id,
                    candidate_id=candidate.id,
                    category=candidate.category,
                    decision="skipped",
                    score=score,
                    reason_code="low_score",
                    reason_text=f"Valor da interrupção abaixo do limiar atual ({minimum_score}).",
                    message_text="",
                    message_id=None,
                    sent_at=None,
                )
                self.store.update_proactive_candidate(
                    candidate_id=candidate.id,
                    cooldown_until=now + timedelta(hours=3),
                )
                continue

            candidate_due_at = candidate.due_at or datetime.max.replace(tzinfo=UTC)
            if (
                best_candidate is None
                or score > best_score
                or (score == best_score and candidate_due_at < (best_due_at or datetime.max.replace(tzinfo=UTC)))
            ):
                best_candidate = candidate
                best_score = score
                best_due_at = candidate_due_at

        if best_candidate is None:
            return

        message_text = await self._compose_candidate_message(
            candidate=best_candidate,
            moment_state=moment_state,
            now=now,
            prefs=prefs,
        )
        if not message_text:
            return

        sent = await self._deliver_candidate_message(
            candidate=best_candidate,
            message_text=message_text,
            prefs=prefs,
            score=best_score,
            moment_state=moment_state,
            now=now,
        )
        if not sent:
            self.store.update_proactive_candidate(
                candidate_id=best_candidate.id,
                cooldown_until=now + timedelta(minutes=90),
            )
            return

        next_status = "sent"
        next_cooldown = now + timedelta(hours=8)
        if best_candidate.status == "confirmed":
            next_cooldown = now + timedelta(hours=12)
        self.store.update_proactive_candidate(
            candidate_id=best_candidate.id,
            status=next_status,
            last_nudged_at=now,
            cooldown_until=next_cooldown,
        )

    def _candidate_enabled(self, *, candidate: ProactiveCandidateRecord, prefs: ProactivePreferencesRecord) -> bool:
        if candidate.category == "agenda_followup":
            return prefs.agenda_enabled
        if candidate.category == "followup":
            return prefs.followups_enabled
        if candidate.category == "project_nudge":
            return prefs.projects_enabled
        if candidate.category == "routine":
            return prefs.routine_enabled
        if candidate.category == "morning_digest":
            return prefs.morning_digest_enabled
        if candidate.category == "night_digest":
            return prefs.night_digest_enabled
        return True

    def _score_candidate(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        now: datetime,
        moment_state: str,
        prefs: ProactivePreferencesRecord,
    ) -> int:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        score = round((candidate.confidence * 0.5) + (candidate.priority * 0.5))
        if candidate.status == "confirmed":
            score += 10
        if candidate.due_at is not None and candidate.due_at <= now:
            score += 8
        if candidate.category == "followup" and payload.get("important_source"):
            score += 18
        if candidate.category == "project_nudge" and payload.get("recent_signal"):
            score += 14
        if candidate.category == "routine":
            score -= 2
        if moment_state == "high_focus":
            score -= 14
        elif moment_state == "available":
            score += 12
        elif moment_state == "low_energy":
            if candidate.category == "routine":
                score += 8
            if candidate.category == "project_nudge":
                score -= 2
        elif moment_state == "busy":
            score -= 4
        if prefs.intensity == "high":
            if candidate.category in {"followup", "project_nudge"}:
                score += 14
            elif candidate.category == "routine":
                score += 8
        elif prefs.intensity == "conservative":
            if candidate.category == "routine":
                score -= 10
            elif candidate.category == "project_nudge":
                score -= 4
        if prefs.presence_mode == "organic":
            if candidate.category == "routine":
                score -= 4
        elif prefs.presence_mode == "active":
            if candidate.category in {"followup", "project_nudge"}:
                score += 4
        score -= self._category_repetition_penalty(category=candidate.category, now=now, prefs=prefs)
        return max(0, min(100, score))

    def _minimum_candidate_score(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        prefs: ProactivePreferencesRecord,
    ) -> int:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        base = 50
        if prefs.intensity == "high":
            base -= 14
        elif prefs.intensity == "conservative":
            base += 8
        if prefs.presence_mode == "organic":
            base += 4
        elif prefs.presence_mode == "active":
            base -= 4
        if candidate.category == "routine":
            base += 4
        if candidate.category == "project_nudge" and prefs.intensity == "conservative":
            base += 2
        if candidate.category == "followup" and payload.get("important_source"):
            base -= 8
        if candidate.status == "confirmed":
            base -= 5
        if candidate.priority >= 88:
            base -= 3
        if candidate.category == "project_nudge" and payload.get("recent_signal"):
            base -= 4
        return max(34, min(70, base))

    async def _compose_candidate_message(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str,
        now: datetime,
        prefs: ProactivePreferencesRecord,
        recent_delivery_examples: list[str] | None = None,
        regeneration_focus: str = "",
    ) -> str:
        owner_context = self._build_owner_proactive_context(now=now)
        voice_profile = self._build_owner_voice_profile(owner_context)
        recent_examples = recent_delivery_examples or self._recent_delivery_examples(limit=RECENT_PROACTIVE_EXAMPLES_LIMIT)
        fallback = self._render_candidate_message(
            candidate=candidate,
            moment_state=moment_state,
            owner_context=owner_context,
            prefs=prefs,
            voice_profile=voice_profile,
            recent_delivery_examples=recent_examples,
        )
        suggested_actions = self._candidate_suggested_actions(candidate)
        try:
            generated = await self.deepseek_service.generate_proactive_message(
                category=candidate.category,
                candidate_title=candidate.title,
                candidate_summary=candidate.summary,
                candidate_status=candidate.status,
                moment_state=moment_state,
                owner_profile_context=self._format_owner_profile_context(owner_context),
                recent_owner_context=self._format_recent_owner_messages_for_prompt(owner_context),
                owner_voice_guidance=voice_profile.guidance,
                project_context=self._build_candidate_project_context(candidate),
                suggested_actions=suggested_actions,
                recent_delivery_examples=recent_examples[:RECENT_PROMPT_EXAMPLES_LIMIT],
                additional_context=self._build_candidate_additional_context(
                    candidate=candidate,
                    moment_state=moment_state,
                    owner_context=owner_context,
                    prefs=prefs,
                    voice_profile=voice_profile,
                ),
                humor_guidance=self._build_humor_guidance(
                    candidate=candidate,
                    moment_state=moment_state,
                    owner_context=owner_context,
                    prefs=prefs,
                    voice_profile=voice_profile,
                ),
                regeneration_focus=regeneration_focus,
            )
        except Exception as exc:
            logger.warning(
                "proactive_message_generation_failed category=%s candidate_id=%s detail=%s",
                candidate.category,
                candidate.id,
                exc,
            )
            return fallback

        normalized = self._sanitize_proactive_message(generated)
        return normalized or fallback

    def _render_candidate_message(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str = "available",
        owner_context: OwnerProactiveContext | None = None,
        prefs: ProactivePreferencesRecord,
        voice_profile: OwnerVoiceProfile | None = None,
        recent_delivery_examples: list[str] | None = None,
    ) -> str:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        direct_tone = voice_profile.prefers_direct if voice_profile is not None else self._prefer_direct_tone(owner_context)
        humor_line = self._fallback_humor_line(
            candidate=candidate,
            moment_state=moment_state,
            owner_context=owner_context,
            prefs=prefs,
            voice_profile=voice_profile,
        )
        if candidate.category == "followup":
            task_text = str(payload.get("task_text") or candidate.title).strip()
            important_reason = str(payload.get("source_reason") or "").strip()
            source_excerpt = str(payload.get("source_excerpt") or "").strip()
            important_source = bool(payload.get("important_source"))
            if important_source:
                intro = important_reason[:140] or task_text[:140]
                if candidate.status == "confirmed":
                    if direct_tone:
                        return (
                            f"Isso ainda merece radar: {intro[:150]}.\n"
                            + (f"Sinal recente: {source_excerpt[:110]}.\n" if source_excerpt else "")
                            + "Se continuar aberto, eu te lembro no melhor momento ou já destrincho o próximo passo."
                            + (f"\n{humor_line}" if humor_line else "")
                        )
                    return (
                        f"Passei aqui porque isso ainda pede atenção de verdade: {intro[:150]}.\n"
                        + (f"O sinal mais claro foi: {source_excerpt[:110]}.\n" if source_excerpt else "")
                        + "Se fizer sentido, eu posso te lembrar no momento certo ou já te devolver isso mastigado no próximo passo."
                        + (f"\n{humor_line}" if humor_line else "")
                    )
                if direct_tone:
                    return (
                        f"Tem uma frente importante pedindo atenção: {intro[:150]}.\n"
                        + (f"Sinal salvo: {source_excerpt[:110]}.\n" if source_excerpt else "")
                        + "Se quiser, eu transformo isso agora em um próximo passo claro."
                        + (f"\n{humor_line}" if humor_line else "")
                    )
                return (
                    f"Quero te poupar carga mental com uma coisa que vale radar agora: {intro[:150]}.\n"
                    + (f"O melhor sinal recente foi: {source_excerpt[:110]}.\n" if source_excerpt else "")
                    + "Se fizer sentido, eu organizo isso em um próximo passo simples em vez de deixar solto."
                    + (f"\n{humor_line}" if humor_line else "")
                )
            if candidate.status == "confirmed":
                if direct_tone:
                    return (
                        f"Segue em radar: {task_text[:150]}.\n"
                        "Quer resolver agora ou prefere que eu só traga isso de volta na hora certa?"
                        + (f"\n{humor_line}" if humor_line else "")
                    )
                return (
                    f"Deixo isso vivo no radar: {task_text[:150]}.\n"
                    "Se ajudar, eu posso te lembrar no momento certo ou te ajudar a reduzir isso ao próximo passo."
                    + (f"\n{humor_line}" if humor_line else "")
                )
            if moment_state == "low_energy":
                return (
                    f"Sem te sobrecarregar: isso continua aberto -> {task_text[:150]}.\n"
                    "Se quiser, eu deixo isso em um próximo passo leve e objetivo."
                    + (f"\n{humor_line}" if humor_line else "")
                )
            return (
                f"Tem uma pendência que vale um toque curto agora: {task_text[:150]}.\n"
                "Se fizer sentido, eu te ajudo a destravar isso em 1 passo só."
                + (f"\n{humor_line}" if humor_line else "")
            )
        if candidate.category == "project_nudge":
            project_name = str(payload.get("project_name") or candidate.title).strip()
            next_step = str(payload.get("next_step") or candidate.summary).strip()
            project_reason = str(payload.get("project_reason") or "").strip()
            suggested_actions = [
                str(item).strip()
                for item in (payload.get("suggested_actions") or [])
                if str(item).strip()
            ][:3]
            lead = (
                f"Passei aqui com um corte rápido de {project_name[:96]}."
                if not direct_tone
                else f"Radar rápido de {project_name[:96]}."
            )
            lines = [lead]
            if project_reason:
                lines.append(f"Motivo: {project_reason[:110]}")
            if next_step:
                lines.append(f"Próximo passo mais claro: {next_step[:120]}")
            if suggested_actions:
                for index, action in enumerate(suggested_actions[:2], start=1):
                    label = "Agora" if index == 1 else "Depois"
                    lines.append(f"{label}: {action[:88]}")
            if moment_state == "low_energy":
                lines.append("Se hoje estiver pesado, eu posso só te deixar isso pronto para retomar sem atrito.")
            else:
                lines.append('Se quiser, eu já converto isso em um plano curto, ou você pode responder "marque como concluído" / "reabra".')
            if humor_line:
                lines.append(humor_line)
            return "\n".join(lines)
        if candidate.category == "routine":
            suggestion = str(payload.get("suggestion") or "Vale reorganizar o próximo bloco com mais leveza.").strip()
            if direct_tone:
                return (
                    f"Senti um sinal de carga mais alta agora: {candidate.summary[:140]}.\n"
                    f"Sugestão enxuta: {suggestion[:140]}"
                    + (f"\n{humor_line}" if humor_line else "")
                )
            return (
                f"Seu ritmo pareceu mais pesado agora: {candidate.summary[:140]}.\n"
                f"Em vez de empilhar mais coisa, talvez valha isto: {suggestion[:140]}"
                + (f"\n{humor_line}" if humor_line else "")
            )
        if candidate.category == "agenda_followup":
            return (
                f"Tem um ponto de agenda que merece um ajuste curto: {candidate.summary[:180]}.\n"
                "Se quiser, eu organizo isso agora do jeito mais simples."
            )
        return candidate.summary[:220]

    def _build_owner_proactive_context(self, *, now: datetime) -> OwnerProactiveContext:
        owner_phone = self._resolve_owner_phone()
        if not owner_phone:
            return OwnerProactiveContext(
                memory=None,
                recent_inbound_lines=[],
                recent_mood_signals=[],
                recent_implied_tasks=[],
                recent_style_hints=[],
            )

        memory = self.store.get_whatsapp_agent_contact_memory(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
        )
        messages = self.store.list_whatsapp_agent_messages_for_contact(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            limit=10,
        )
        recent_inbound_lines: list[str] = []
        recent_mood_signals: list[str] = []
        recent_implied_tasks: list[str] = []
        recent_style_hints: list[str] = []
        recent_cutoff = now - timedelta(hours=16)

        for message in messages:
            if message.direction != "inbound" or message.message_timestamp < recent_cutoff:
                continue
            content = self._summarize_text(message.content, 140)
            if content:
                recent_inbound_lines.append(content)
            metadata = message.metadata if isinstance(message.metadata, dict) else {}
            recent_mood_signals.extend(
                str(item).strip()
                for item in (metadata.get("agent_mood_signals") or [])
                if str(item).strip()
            )
            recent_implied_tasks.extend(
                str(item).strip()
                for item in (metadata.get("agent_implied_tasks") or [])
                if str(item).strip()
            )
            style_hint = str(metadata.get("agent_writing_style_hints") or "").strip()
            if style_hint:
                recent_style_hints.append(style_hint)

        return OwnerProactiveContext(
            memory=memory,
            recent_inbound_lines=recent_inbound_lines[-4:],
            recent_mood_signals=self._dedupe_text_list(recent_mood_signals, limit=4),
            recent_implied_tasks=self._dedupe_text_list(recent_implied_tasks, limit=5),
            recent_style_hints=self._dedupe_text_list(recent_style_hints, limit=3),
        )

    def _format_owner_profile_context(self, owner_context: OwnerProactiveContext) -> str:
        memory = owner_context.memory
        if memory is None:
            return ""
        parts: list[str] = []
        if memory.profile_summary:
            parts.append(f"Resumo pessoal: {memory.profile_summary}")
        if memory.preferred_tone:
            parts.append(f"Tom preferido: {memory.preferred_tone}")
        if memory.preferences:
            parts.append("Preferencias: " + "; ".join(memory.preferences[:4]))
        if memory.objectives:
            parts.append("Objetivos recorrentes: " + "; ".join(memory.objectives[:4]))
        if memory.constraints:
            parts.append("Restricoes: " + "; ".join(memory.constraints[:3]))
        if memory.recurring_instructions:
            parts.append("Instrucoes recorrentes: " + "; ".join(memory.recurring_instructions[:3]))
        if owner_context.recent_style_hints:
            parts.append("Estilo recente de escrita: " + "; ".join(owner_context.recent_style_hints[:2]))
        return "\n".join(parts).strip()

    def _format_recent_owner_messages_for_prompt(self, owner_context: OwnerProactiveContext) -> str:
        lines = [f"- {line}" for line in owner_context.recent_inbound_lines if line]
        if owner_context.recent_mood_signals:
            lines.append("Sinais de humor recentes: " + "; ".join(owner_context.recent_mood_signals[:3]))
        if owner_context.recent_implied_tasks:
            lines.append("Acoes implicitas recentes: " + "; ".join(owner_context.recent_implied_tasks[:3]))
        return "\n".join(lines).strip()

    def _build_candidate_project_context(self, candidate: ProactiveCandidateRecord) -> str:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        project_key = str(payload.get("project_key") or "").strip()
        if not project_key:
            return ""
        project = next(
            (
                item
                for item in self.store.list_project_memories(self.settings.default_user_id, limit=32)
                if item.project_key == project_key
            ),
            None,
        )
        if project is None:
            return ""
        return self._build_project_action_context(project)

    def _candidate_suggested_actions(self, candidate: ProactiveCandidateRecord) -> list[str]:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        actions = [
            str(item).strip()
            for item in (payload.get("suggested_actions") or [])
            if str(item).strip()
        ]
        if actions:
            return actions[:3]
        next_step = str(payload.get("next_step") or "").strip()
        if next_step:
            return [next_step[:120]]
        return []

    def _build_candidate_additional_context(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str,
        owner_context: OwnerProactiveContext,
        prefs: ProactivePreferencesRecord,
        voice_profile: OwnerVoiceProfile,
    ) -> str:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        parts = [
            f"Momento atual detectado: {moment_state}",
            f"Modo de presenca desejado: {prefs.presence_mode}",
            f"Humor configurado: {prefs.humor_style}",
            f"Voz desejada: {voice_profile.guidance}",
        ]
        if owner_context.recent_mood_signals:
            parts.append("Humor recente: " + "; ".join(owner_context.recent_mood_signals[:3]))
        if owner_context.recent_implied_tasks:
            parts.append("Acoes que o dono parece estar tentando mover: " + "; ".join(owner_context.recent_implied_tasks[:3]))
        if candidate.category == "followup" and payload.get("important_source"):
            parts.append("Esta iniciativa vem de um sinal importante salvo no radar.")
        if candidate.category == "project_nudge" and payload.get("recent_signal"):
            parts.append("Ha sinal recente conectando este projeto ao momento atual.")
        if candidate.status == "confirmed":
            parts.append("O dono ja demonstrou abertura para esse assunto; pode soar um pouco mais assertivo sem perder delicadeza.")
        return "\n".join(parts)

    def _build_humor_guidance(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str,
        owner_context: OwnerProactiveContext,
        prefs: ProactivePreferencesRecord,
        voice_profile: OwnerVoiceProfile,
    ) -> str:
        if not self._humor_allowed(
            candidate=candidate,
            moment_state=moment_state,
            owner_context=owner_context,
            prefs=prefs,
            voice_profile=voice_profile,
        ):
            return "Nao usar humor nesta mensagem."
        if prefs.humor_style == "playful":
            return (
                "Humor permitido com leveza controlada: no maximo uma linha curta no fim, "
                "com ironia gentil e humana, sem virar personagem nem deboche."
            )
        if candidate.category == "project_nudge":
            return (
                "Humor permitido em dose homeopatica: no maximo uma linha curta no final, "
                "seca e inteligente, como alivio leve de tensao sobre atrito, backlog ou inercia. Nada teatral."
            )
        if candidate.category == "routine":
            return (
                "Humor permitido de forma acolhedora: no maximo uma linha curta que reduza a pressao sem parecer deboche."
            )
        return (
            "Humor opcional e minimo: no maximo uma linha curta no fim, com ironia gentil ou leveza seca."
        )

    def _build_owner_voice_profile(self, owner_context: OwnerProactiveContext) -> OwnerVoiceProfile:
        prefers_direct = self._prefer_direct_tone(owner_context)
        prefers_formal = self._owner_prefers_formal_style(owner_context)
        prefers_playful = self._owner_prefers_playful_style(owner_context)
        descriptors: list[str] = []
        if prefers_direct:
            descriptors.append("soar direto, curto e sem rodeios")
        else:
            descriptors.append("soar conversacional, natural e sem cara de painel")
        if prefers_formal:
            descriptors.append("manter sobriedade e evitar gracinha")
        elif prefers_playful:
            descriptors.append("aceitar leveza curta quando o momento estiver leve")
        else:
            descriptors.append("preferir calor humano discreto")
        if owner_context.recent_style_hints:
            descriptors.append("seguir o ritmo recente de escrita do dono")
        return OwnerVoiceProfile(
            guidance="; ".join(descriptors),
            prefers_direct=prefers_direct,
            prefers_playful=prefers_playful,
            prefers_formal=prefers_formal,
        )

    def _prefer_direct_tone(self, owner_context: OwnerProactiveContext | None) -> bool:
        if owner_context is None:
            return False
        memory = owner_context.memory
        clues: list[str] = list(owner_context.recent_style_hints)
        if memory is not None and memory.preferred_tone:
            clues.append(memory.preferred_tone)
        clues.extend(owner_context.recent_inbound_lines[:2])
        normalized = " ".join(clues).lower()
        return any(marker in normalized for marker in ("direto", "curto", "objetivo", "pratico", "prático"))

    def _owner_prefers_formal_style(self, owner_context: OwnerProactiveContext | None) -> bool:
        if owner_context is None:
            return False
        clues: list[str] = list(owner_context.recent_style_hints)
        if owner_context.memory is not None and owner_context.memory.preferred_tone:
            clues.append(owner_context.memory.preferred_tone)
        normalized = " ".join(clues).lower()
        return any(marker in normalized for marker in ("formal", "sobrio", "sÃ³brio", "profissional", "serio", "sÃ©rio"))

    def _owner_prefers_playful_style(self, owner_context: OwnerProactiveContext | None) -> bool:
        if owner_context is None:
            return False
        normalized = " ".join([*owner_context.recent_style_hints, *owner_context.recent_inbound_lines]).lower()
        return any(marker in normalized for marker in ("kk", "haha", "rs", "leve", "humor", "brinca", "emoji"))

    def _humor_allowed(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str,
        owner_context: OwnerProactiveContext | None,
        prefs: ProactivePreferencesRecord,
        voice_profile: OwnerVoiceProfile,
    ) -> bool:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        if prefs.humor_style == "off":
            return False
        if candidate.category == "agenda_followup":
            return False
        if candidate.category not in {"project_nudge", "routine", "followup"}:
            return False
        if payload.get("important_source"):
            return False
        if candidate.priority >= 82:
            return False
        if moment_state in {"high_focus", "busy"}:
            return False
        if voice_profile.prefers_formal:
            return False
        if owner_context is not None and owner_context.recent_mood_signals:
            normalized_mood = " ".join(owner_context.recent_mood_signals).lower()
            if any(marker in normalized_mood for marker in ("frustr", "ansios", "exaust", "sobrecarreg", "pression")):
                return False
        if candidate.category == "followup" and not voice_profile.prefers_playful and prefs.humor_style == "subtle":
            return False
        return True

    def _fallback_humor_line(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str,
        owner_context: OwnerProactiveContext | None,
        prefs: ProactivePreferencesRecord,
        voice_profile: OwnerVoiceProfile | None,
    ) -> str:
        effective_voice = voice_profile or self._build_owner_voice_profile(
            owner_context
            or OwnerProactiveContext(
                memory=None,
                recent_inbound_lines=[],
                recent_mood_signals=[],
                recent_implied_tasks=[],
                recent_style_hints=[],
            )
        )
        if not self._humor_allowed(
            candidate=candidate,
            moment_state=moment_state,
            owner_context=owner_context,
            prefs=prefs,
            voice_profile=effective_voice,
        ):
            return ""
        variants: list[str]
        if candidate.category == "project_nudge":
            variants = [
                "Se a inercia estiver bem instalada hoje, eu posso dar um empurrao civilizado.",
                "Prometo manter isso abaixo do limite entre progresso real e backlog decorativo.",
                "Isso ainda parece mais perto de andar do que de virar peca de museu.",
            ]
        elif candidate.category == "routine":
            variants = [
                "Seu cerebro talvez mereca um cafe e uma tregua diplomatica ao mesmo tempo.",
                "Hoje talvez nao seja dia de competir com a propria bateria em modo economia.",
                "A meta aqui e progresso com dignidade, nao heroismo administrativo.",
            ]
        else:
            variants = [
                "Melhor mexer nisso antes que vire morador fixo do backlog.",
                "Da para resolver isso antes de virar patrimonio emocional da semana.",
                "A ideia e fechar isso enquanto ainda cabe num gesto curto.",
            ]
        index_seed = f"{candidate.id}:{candidate.category}:{moment_state}:{prefs.humor_style}"
        index = int(hashlib.sha1(index_seed.encode("utf-8")).hexdigest(), 16) % len(variants)
        return variants[index]

    def _sanitize_proactive_message(self, value: str) -> str:
        text = str(value or "").replace("\r", "\n").strip().strip('"').strip("'")
        lines = [" ".join(line.split()).strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        normalized = "\n".join(lines).strip()
        if not normalized:
            return ""
        if len(normalized) > 520:
            normalized = normalized[:517].rstrip(" .,;:") + "..."
        return normalized

    def _dedupe_text_list(self, items: list[str], *, limit: int) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            normalized = " ".join(str(item).split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(normalized[:140])
            if len(result) >= limit:
                break
        return result

    def _build_candidate_priority_context(self, candidate: ProactiveCandidateRecord) -> str:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        if candidate.category == "project_nudge":
            project_name = str(payload.get("project_name") or candidate.title).strip()
            next_step = str(payload.get("next_step") or candidate.summary).strip()
            project_reason = str(payload.get("project_reason") or candidate.summary).strip()
            suggested_actions = [
                str(item).strip()
                for item in (payload.get("suggested_actions") or [])
                if str(item).strip()
            ][:2]
            lines = [
                "Esta mensagem pode ser resposta a um nudge recente de projeto.",
                f"Projeto em foco: {project_name[:100]}",
                f"Motivo do radar: {project_reason[:140]}",
            ]
            if next_step:
                lines.append(f"Proximo passo mais claro: {next_step[:140]}")
            if suggested_actions:
                lines.append("Acoes sugeridas: " + "; ".join(action[:88] for action in suggested_actions))
            return "\n".join(lines)
        if candidate.category == "followup":
            task_text = str(payload.get("task_text") or candidate.summary or candidate.title).strip()
            return "\n".join(
                [
                    "Esta mensagem pode ser resposta a uma pendencia recente em radar.",
                    f"Pendencia em foco: {task_text[:160]}",
                ]
            )
        if candidate.category == "agenda_followup":
            return "\n".join(
                [
                    "Esta mensagem pode ser resposta a um item recente de agenda.",
                    f"Contexto em foco: {candidate.summary[:160]}",
                ]
            )
        return ""

    async def _generate_project_action_hints(self, *, project: ProjectMemoryRecord) -> list[str]:
        fallback_actions = self._fallback_project_action_hints(project)
        project_context = self._build_project_action_context(project)
        owner_context = self._build_recent_owner_context()
        try:
            result = await self.deepseek_service.extract_project_action_hints(
                project_context=project_context,
                owner_context=owner_context,
            )
        except Exception as exc:
            logger.warning("proactive_project_action_hints_failed project_key=%s detail=%s", project.project_key, exc)
            return fallback_actions
        if result.suggested_actions:
            return result.suggested_actions[:3]
        return fallback_actions

    def _build_project_action_context(self, project: ProjectMemoryRecord) -> str:
        lines = [
            f"Projeto: {project.project_name}",
            f"Resumo: {project.summary or '(sem resumo)'}",
        ]
        if project.status:
            lines.append(f"Status: {project.status}")
        if project.what_is_being_built:
            lines.append(f"O que esta sendo desenvolvido: {project.what_is_being_built}")
        if project.built_for:
            lines.append(f"Para quem: {project.built_for}")
        if project.next_steps:
            lines.append("Proximos passos: " + "; ".join(project.next_steps[:3]))
        if project.evidence:
            lines.append("Evidencias: " + "; ".join(project.evidence[:2]))
        return "\n".join(lines)

    def _build_recent_owner_context(self) -> str:
        owner_phone = self._resolve_owner_phone()
        if not owner_phone:
            return ""
        messages = self.store.list_whatsapp_agent_messages_for_contact(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            limit=6,
        )
        lines: list[str] = []
        for message in messages:
            if message.direction != "inbound":
                continue
            content = " ".join(message.content.split()).strip()
            if not content:
                continue
            lines.append(f"- {content[:140]}")
            if len(lines) >= 3:
                break
        return "\n".join(lines)

    def _fallback_project_action_hints(self, project: ProjectMemoryRecord) -> list[str]:
        actions: list[str] = []
        if project.next_steps:
            actions.append(project.next_steps[0].strip())
        if project.built_for:
            actions.append(f"Escrever em 3 linhas a entrega exata para {project.built_for[:60]}.")
        if project.what_is_being_built:
            actions.append(f"Listar os 2 blocos que faltam para fechar {project.project_name[:60]}.")
        if not actions:
            actions.append(f"Definir o proximo passo executavel de {project.project_name[:60]} em uma frase.")
        deduped: list[str] = []
        seen: set[str] = set()
        for action in actions:
            normalized = " ".join(action.split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized[:120])
            if len(deduped) >= 3:
                break
        return deduped

    def _seed_important_followups_if_needed(
        self,
        *,
        prefs: ProactivePreferencesRecord,
        now: datetime,
    ) -> None:
        if not prefs.followups_enabled:
            return

        open_candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=80,
            statuses=["suggested", "sent", "confirmed"],
            categories=["followup"],
        )
        closed_candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=80,
            statuses=["dismissed", "done", "expired"],
            categories=["followup"],
        )
        refreshable_candidates = [candidate for candidate in open_candidates if candidate.status == "suggested"]
        important_messages = self.store.list_important_messages(self.settings.default_user_id, limit=10)
        if not important_messages:
            return

        created = 0
        for message in important_messages:
            candidate_data = self._build_important_followup_candidate(message=message, now=now)
            if candidate_data is None:
                continue
            payload = candidate_data.get("payload_json") if isinstance(candidate_data.get("payload_json"), dict) else {}
            dedupe_key = str(payload.get("dedupe_key") or "").strip()
            existing = self._find_candidate_by_dedupe_key(
                candidates=[*open_candidates, *closed_candidates],
                dedupe_key=dedupe_key,
            )
            if existing is not None:
                if existing.status == "suggested":
                    updated = self._create_or_refresh_candidate(
                        active_candidates=refreshable_candidates,
                        candidate_data=candidate_data,
                    )
                    refreshable_candidates = [
                        updated if candidate.id == updated.id else candidate
                        for candidate in refreshable_candidates
                    ]
                continue
            created_candidate = self._create_or_refresh_candidate(
                active_candidates=refreshable_candidates,
                candidate_data=candidate_data,
            )
            refreshable_candidates.append(created_candidate)
            open_candidates.append(created_candidate)
            created += 1
            if created >= 4:
                break

    def _build_important_followup_candidate(
        self,
        *,
        message: ImportantMessageRecord,
        now: datetime,
    ) -> dict[str, Any] | None:
        if message.status != "active":
            return None
        if message.message_timestamp < now - timedelta(hours=IMPORTANT_MESSAGE_CANDIDATE_HOURS):
            return None
        reason = message.importance_reason.strip()
        if not reason:
            return None

        normalized_category = str(message.category or "").strip().lower()
        confidence = max(68, min(96, int(message.confidence or 0)))
        priority = self._important_priority_for_category(normalized_category)
        due_delay = self._important_due_delay(normalized_category)
        due_at = message.message_timestamp + due_delay

        task_text = reason[:180]
        excerpt = self._summarize_text(message.message_text, 160)
        return {
            "category": "followup",
            "status": "suggested",
            "source_message_id": message.source_message_id,
            "source_kind": "important_message",
            "thread_id": None,
            "contact_phone": self._resolve_owner_phone(),
            "chat_jid": self._resolve_recent_owner_chat_target(now=now),
            "title": f"Prioridade em aberto: {task_text[:88]}".strip(),
            "summary": f"{reason[:160]} | {excerpt[:80]}".strip(" |"),
            "confidence": confidence,
            "priority": priority,
            "due_at": due_at,
            "cooldown_until": due_at,
            "last_nudged_at": None,
            "payload_json": {
                "dedupe_key": f"important:{message.source_message_id}",
                "task_text": task_text,
                "source_category": normalized_category,
                "source_reason": reason[:180],
                "source_excerpt": excerpt,
                "important_source": True,
            },
        }

    def _important_priority_for_category(self, category: str) -> int:
        if category in {"deadline", "risk"}:
            return 92
        if category in {"money", "access"}:
            return 86
        if category in {"document", "client", "project"}:
            return 80
        return 72

    def _important_due_delay(self, category: str) -> timedelta:
        if category in {"deadline", "risk"}:
            return timedelta(minutes=35)
        if category in {"money", "access"}:
            return timedelta(hours=1)
        if category in {"document", "client", "project"}:
            return timedelta(hours=2)
        return timedelta(hours=4)

    def _select_project_for_nudge(
        self,
        *,
        projects: list[ProjectMemoryRecord],
        important_messages: list[ImportantMessageRecord],
        now: datetime,
    ) -> tuple[ProjectMemoryRecord, list[ImportantMessageRecord], int] | None:
        ranked: list[tuple[int, ProjectMemoryRecord, list[ImportantMessageRecord]]] = []
        for project in projects:
            related_signals = [
                message
                for message in important_messages
                if self._important_message_relates_to_project(message=message, project=project)
            ]
            score = 0
            status = project.status.strip().lower()
            stage = project.stage.strip().lower()
            priority = project.priority.strip().lower()
            if project.next_steps:
                score += 24
            if project.what_is_being_built:
                score += 14
            if project.built_for:
                score += 8
            if project.evidence:
                score += min(10, len(project.evidence) * 3)
            if project.blockers:
                score += min(14, len(project.blockers) * 5)
            score += min(16, max(0, project.confidence_score) // 6)
            if any(marker in status for marker in ("ativo", "andamento", "fazendo", "aberto", "execu")):
                score += 14
            if any(marker in status for marker in ("concl", "finaliz", "done", "encerr")):
                score -= 18
            if stage == "blocked":
                score += 10
            elif stage in {"review", "active"}:
                score += 6
            if priority == "high":
                score += 10
            elif priority == "medium":
                score += 4
            pivot = project.last_material_update_at or project.last_seen_at or project.updated_at
            if pivot is not None:
                hours_since_pivot = max(0.0, (now - pivot).total_seconds() / 3600)
                if hours_since_pivot >= PROJECT_STALE_NUDGE_HOURS:
                    score += 18
                elif hours_since_pivot >= 8:
                    score += 10
                else:
                    score += 4
            if related_signals:
                score += min(24, len(related_signals) * 8)
                if any(message.category in {"deadline", "risk", "client"} for message in related_signals):
                    score += 10
            if score > 0:
                ranked.append((score, project, related_signals))

        if not ranked:
            return None
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].last_seen_at or item[1].updated_at,
            ),
            reverse=True,
        )
        top_score, top_project, top_related_signals = ranked[0]
        return top_project, top_related_signals[:2], top_score

    def _describe_project_signal(
        self,
        *,
        project: ProjectMemoryRecord,
        related_signals: list[ImportantMessageRecord],
    ) -> str:
        if related_signals:
            top_signal = related_signals[0]
            return f"houve sinal recente de {top_signal.category}: {top_signal.importance_reason[:90]}"
        if project.next_steps:
            return f"ja existe proximo passo claro: {project.next_steps[0][:90]}"
        if project.last_seen_at is not None:
            local_seen = project.last_seen_at.astimezone(DEFAULT_TIMEZONE).strftime("%d/%m %H:%M")
            return f"frente ativa sem revisao recente desde {local_seen}"
        return "frente ativa pedindo fechamento do proximo passo"

    def _important_message_relates_to_project(
        self,
        *,
        message: ImportantMessageRecord,
        project: ProjectMemoryRecord,
    ) -> bool:
        haystack = f"{message.importance_reason} {message.message_text}".lower()
        project_name = project.project_name.strip().lower()
        if project_name and project_name in haystack:
            return True
        tokens = [
            token
            for token in re.split(r"[^a-z0-9]+", project_name)
            if len(token) >= 4 and token not in {"projeto", "sistema", "site", "painel", "app", "api"}
        ]
        if not tokens:
            return False
        matches = sum(1 for token in tokens if token in haystack)
        return matches >= min(2, len(tokens))

    def _summarize_text(self, value: str, max_chars: int) -> str:
        normalized = " ".join(str(value or "").split()).strip()
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max(0, max_chars - 3)].rstrip() + "..."

    def _find_candidate_by_dedupe_key(
        self,
        *,
        candidates: list[ProactiveCandidateRecord],
        dedupe_key: str,
    ) -> ProactiveCandidateRecord | None:
        normalized_key = dedupe_key.strip()
        if not normalized_key:
            return None
        for candidate in candidates:
            payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
            if str(payload.get("dedupe_key") or "").strip() == normalized_key:
                return candidate
        return None

    def _candidate_can_bypass_soft_holds(self, candidate: ProactiveCandidateRecord) -> bool:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        return (
            candidate.status == "confirmed"
            or bool(payload.get("important_source"))
            or candidate.priority >= 92
        )

    def _recent_sent_deliveries(self, *, limit: int = RECENT_PROACTIVE_EXAMPLES_LIMIT) -> list[ProactiveDeliveryLogRecord]:
        return self.store.list_recent_proactive_deliveries(
            user_id=self.settings.default_user_id,
            limit=limit,
            decisions=["sent"],
        )

    def _recent_delivery_examples(self, *, limit: int = RECENT_PROACTIVE_EXAMPLES_LIMIT) -> list[str]:
        examples: list[str] = []
        for delivery in self._recent_sent_deliveries(limit=limit):
            text = self._summarize_text(delivery.message_text, 220).strip()
            if text:
                examples.append(text)
        return examples

    def _normalize_message_for_similarity(self, value: str) -> str:
        normalized = " ".join(str(value or "").lower().split()).strip()
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
        return normalized

    def _find_similar_recent_delivery(
        self,
        *,
        message_text: str,
        recent_deliveries: list[ProactiveDeliveryLogRecord],
    ) -> tuple[ProactiveDeliveryLogRecord | None, float]:
        target = self._normalize_message_for_similarity(message_text)
        if not target:
            return None, 0.0
        best_delivery: ProactiveDeliveryLogRecord | None = None
        best_score = 0.0
        for delivery in recent_deliveries:
            source = self._normalize_message_for_similarity(delivery.message_text)
            if not source:
                continue
            score = SequenceMatcher(None, target, source).ratio()
            if score > best_score:
                best_delivery = delivery
                best_score = score
        return best_delivery, best_score

    def _category_repetition_penalty(
        self,
        *,
        category: str,
        now: datetime,
        prefs: ProactivePreferencesRecord,
    ) -> int:
        base_penalty = 12 if prefs.presence_mode == "organic" else 8 if prefs.presence_mode == "balanced" else 4
        penalty = 0
        for index, delivery in enumerate(self._recent_sent_deliveries(limit=3)):
            if delivery.category != category:
                continue
            age_minutes = max(0.0, (now - delivery.created_at).total_seconds() / 60)
            if age_minutes > 18 * 60:
                continue
            penalty += max(2, base_penalty - (index * 2))
        return penalty

    def _organic_jitter_minutes(self, *, category: str, stable_key: str) -> int:
        low, high = ORGANIC_JITTER_WINDOWS.get(category, (5, 12))
        if high <= low:
            return low
        digest = hashlib.sha1(f"{self.settings.default_user_id}:{category}:{stable_key}".encode("utf-8")).hexdigest()
        offset = int(digest[:8], 16) % (high - low + 1)
        return low + offset

    def _organic_jitter_suppression(
        self,
        *,
        category: str,
        stable_key: str,
        due_at: datetime,
        now: datetime,
    ) -> tuple[str, str, datetime] | None:
        jitter_minutes = self._organic_jitter_minutes(category=category, stable_key=stable_key)
        release_at = due_at + timedelta(minutes=jitter_minutes)
        if now >= release_at:
            return None
        remaining_minutes = max(1, int(((release_at - now).total_seconds() + 59) // 60))
        return (
            "organic_jitter_wait",
            f"Janela organica segurando esse envio por mais cerca de {remaining_minutes} min.",
            release_at,
        )

    async def _stabilize_message_variation(
        self,
        *,
        message_text: str,
        recent_deliveries: list[ProactiveDeliveryLogRecord],
        regenerate_message: Callable[[str], Awaitable[str]],
        fallback_message: str,
    ) -> str | None:
        _, similarity = self._find_similar_recent_delivery(message_text=message_text, recent_deliveries=recent_deliveries)
        if similarity <= MESSAGE_SIMILARITY_THRESHOLD:
            return message_text

        regeneration_focus = "Evite repetir abertura, estrutura ou ritmo de uma mensagem proativa muito recente."
        regenerated = self._sanitize_proactive_message(await regenerate_message(regeneration_focus))
        if regenerated:
            _, regenerated_similarity = self._find_similar_recent_delivery(
                message_text=regenerated,
                recent_deliveries=recent_deliveries,
            )
            if regenerated_similarity <= MESSAGE_SIMILARITY_THRESHOLD:
                return regenerated

        fallback = self._sanitize_proactive_message(fallback_message)
        if fallback:
            _, fallback_similarity = self._find_similar_recent_delivery(
                message_text=fallback,
                recent_deliveries=recent_deliveries,
            )
            if fallback_similarity <= MESSAGE_SIMILARITY_THRESHOLD:
                return fallback
        return None

    async def _deliver_candidate_message(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        message_text: str,
        prefs: ProactivePreferencesRecord,
        score: int,
        moment_state: str,
        now: datetime,
    ) -> bool:
        recent_deliveries = self._recent_sent_deliveries()
        owner_context = self._build_owner_proactive_context(now=now)
        voice_profile = self._build_owner_voice_profile(owner_context)
        fallback_message = self._render_candidate_message(
            candidate=candidate,
            moment_state=moment_state,
            owner_context=owner_context,
            prefs=prefs,
            voice_profile=voice_profile,
            recent_delivery_examples=[delivery.message_text for delivery in recent_deliveries],
        )
        stabilized = await self._stabilize_message_variation(
            message_text=message_text,
            recent_deliveries=recent_deliveries,
            regenerate_message=lambda regeneration_focus: self._compose_candidate_message(
                candidate=candidate,
                moment_state=moment_state,
                now=now,
                prefs=prefs,
                recent_delivery_examples=[delivery.message_text for delivery in recent_deliveries],
                regeneration_focus=regeneration_focus,
            ),
            fallback_message=fallback_message,
        )
        if not stabilized:
            self.store.create_proactive_delivery_log(
                user_id=self.settings.default_user_id,
                candidate_id=candidate.id,
                category=candidate.category,
                decision="skipped",
                score=score,
                reason_code="repeat_pattern_risk",
                reason_text="Texto proativo ficou parecido demais com envios recentes; melhor nao soar automatico.",
                message_text="",
                message_id=None,
                sent_at=None,
            )
            return False
        return await self._send_unsolicited_message(
            category=candidate.category,
            message_text=stabilized,
            reason_code="candidate_due",
            reason_text=f"{candidate.summary or candidate.title} [moment={moment_state}]",
            score=score,
            candidate_id=candidate.id,
            now=now,
        )

    async def _attempt_digest_delivery(
        self,
        *,
        category: str,
        digest_payload: dict[str, Any],
        signature: str,
        prefs: ProactivePreferencesRecord,
        now: datetime,
        score: int,
        reason_text: str,
        scheduled_time_text: str,
    ) -> bool:
        local_now = now.astimezone(DEFAULT_TIMEZONE)
        scheduled_at = datetime.combine(local_now.date(), self._parse_local_time(scheduled_time_text), tzinfo=DEFAULT_TIMEZONE).astimezone(UTC)
        jitter_suppression = self._organic_jitter_suppression(
            category=category,
            stable_key=f"{category}:{signature}:{local_now.date().isoformat()}",
            due_at=scheduled_at,
            now=now,
        )
        if jitter_suppression is not None:
            return False
        recent_owner_inbound = self._recent_owner_inbound_activity(now=now)
        recent_activity_suppression = self._recent_owner_activity_suppression(
            category=category,
            now=now,
            recent_owner_inbound=recent_owner_inbound,
            can_bypass=False,
        )
        if recent_activity_suppression is not None:
            return False
        last_sent_delivery = self._last_sent_delivery()
        unanswered_nudge_suppression = self._unanswered_previous_nudge_suppression(
            category=category,
            now=now,
            last_sent_delivery=last_sent_delivery,
            can_bypass=False,
        )
        if unanswered_nudge_suppression is not None:
            return False
        interval_suppression = self._min_interval_suppression(
            category=category,
            prefs=prefs,
            now=now,
            last_sent_delivery=last_sent_delivery,
            can_bypass=False,
        )
        if interval_suppression is not None:
            return False

        recent_deliveries = self._recent_sent_deliveries()
        message_text = await self._compose_digest_message(
            category=category,
            digest_payload=digest_payload,
            prefs=prefs,
            now=now,
            recent_delivery_examples=[delivery.message_text for delivery in recent_deliveries],
        )
        if not message_text:
            return False
        fallback_message = self._render_digest_message(category=category, digest_payload=digest_payload)
        stabilized = await self._stabilize_message_variation(
            message_text=message_text,
            recent_deliveries=recent_deliveries,
            regenerate_message=lambda regeneration_focus: self._compose_digest_message(
                category=category,
                digest_payload=digest_payload,
                prefs=prefs,
                now=now,
                recent_delivery_examples=[delivery.message_text for delivery in recent_deliveries],
                regeneration_focus=regeneration_focus,
            ),
            fallback_message=fallback_message,
        )
        if not stabilized:
            self.store.create_proactive_delivery_log(
                user_id=self.settings.default_user_id,
                candidate_id=None,
                category=category,
                decision="skipped",
                score=score,
                reason_code="repeat_pattern_risk",
                reason_text="Digest ficou parecido demais com envios recentes; melhor segurar para nao soar automatico.",
                message_text="",
                message_id=None,
                sent_at=None,
            )
            return False
        return await self._send_unsolicited_message(
            category=category,
            message_text=stabilized,
            reason_code="scheduled_digest",
            reason_text=reason_text,
            score=score,
            candidate_id=None,
            now=now,
        )

    async def _compose_digest_message(
        self,
        *,
        category: str,
        digest_payload: dict[str, Any],
        prefs: ProactivePreferencesRecord,
        now: datetime,
        recent_delivery_examples: list[str] | None = None,
        regeneration_focus: str = "",
    ) -> str:
        owner_context = self._build_owner_proactive_context(now=now)
        voice_profile = self._build_owner_voice_profile(owner_context)
        fallback_message = self._render_digest_message(category=category, digest_payload=digest_payload)
        facts = [
            str(item).strip()
            for item in (digest_payload.get("facts") or [])
            if str(item).strip()
        ]
        try:
            generated = await self.deepseek_service.generate_proactive_message(
                category=category,
                candidate_title=str(digest_payload.get("title") or "Digest curto").strip(),
                candidate_summary=str(digest_payload.get("summary") or "Resumo curto do radar.").strip(),
                candidate_status="scheduled",
                moment_state=self._detect_moment_state(now=now),
                owner_profile_context=self._format_owner_profile_context(owner_context),
                recent_owner_context=self._format_recent_owner_messages_for_prompt(owner_context),
                owner_voice_guidance=voice_profile.guidance,
                project_context="",
                suggested_actions=[],
                recent_delivery_examples=(recent_delivery_examples or [])[:RECENT_PROMPT_EXAMPLES_LIMIT],
                additional_context="\n".join(
                    [
                        f"Modo de presenca desejado: {prefs.presence_mode}",
                        f"Humor configurado: {prefs.humor_style}",
                        "Fatos estruturados do digest:",
                        *[f"- {fact}" for fact in facts[:6]],
                    ]
                ),
                humor_guidance="Nao usar humor se isso deixar o digest com cara de abertura pronta. Priorize calor humano discreto.",
                regeneration_focus=regeneration_focus,
            )
        except Exception as exc:
            logger.warning("proactive_digest_generation_failed category=%s detail=%s", category, exc)
            return fallback_message
        normalized = self._sanitize_proactive_message(generated)
        return normalized or fallback_message

    def _render_digest_message(self, *, category: str, digest_payload: dict[str, Any]) -> str:
        facts = [
            str(item).strip()
            for item in (digest_payload.get("facts") or [])
            if str(item).strip()
        ]
        opening_variants = {
            "morning_digest": [
                "Bom dia. Separei so o essencial para o comeco do dia ficar leve.",
                "Antes do dia acelerar, deixei um radar curto do que merece ficar vivo.",
                "Passei aqui com um recorte enxuto para abrir o dia sem peso.",
            ],
            "night_digest": [
                "Fechando o dia, deixei so o que vale continuar vivo amanha.",
                "Antes de encerrar, ficou este recorte curto do que ainda importa.",
                "Para nao deixar o dia virar ruido, organizei o essencial de forma enxuta.",
            ],
        }
        variants = opening_variants.get(category, ["Deixei um recorte curto do radar atual."])
        seed = f"{category}:{digest_payload.get('signature') or digest_payload.get('title') or 'digest'}"
        index = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(variants)
        lines = [variants[index]]
        lines.extend(facts[:4])
        return "\n".join(lines)

    def _detect_moment_state(self, *, now: datetime) -> str:
        owner_phone = self._resolve_owner_phone()
        local_hour = now.astimezone(DEFAULT_TIMEZONE).hour
        if not owner_phone:
            return "low_energy" if local_hour >= 22 or local_hour < 7 else "available"

        messages = self.store.list_whatsapp_agent_messages_for_contact(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            limit=12,
        )
        inbound_recent = [
            message
            for message in messages
            if message.direction == "inbound" and message.message_timestamp >= now - timedelta(minutes=90)
        ]
        very_recent = [
            message
            for message in inbound_recent
            if message.message_timestamp >= now - timedelta(minutes=12)
        ]
        mood_signals: list[str] = []
        urgency_signals: list[str] = []
        focus_markers = ("foco", "concentr", "mergulh", "finalizando", "codando", "escrevendo", "produzindo")
        busy_markers = ("corrido", "ocupado", "sem tempo", "depois", "reuniao", "reunião", "call")
        low_energy_markers = ("cans", "exaust", "sono", "sobrecarreg", "estress", "ansios")

        for message in inbound_recent:
            metadata = message.metadata if isinstance(message.metadata, dict) else {}
            mood_signals.extend(str(item).strip().lower() for item in (metadata.get("agent_mood_signals") or []) if str(item).strip())
            urgency = str(metadata.get("agent_implied_urgency") or "").strip().lower()
            if urgency:
                urgency_signals.append(urgency)

        latest_content = " ".join((inbound_recent[0].content if inbound_recent else "").lower().split())
        if any(marker in latest_content for marker in focus_markers) or any("alta" in item for item in urgency_signals):
            return "high_focus"
        if any(marker in latest_content for marker in low_energy_markers) or any(
            any(marker in signal for marker in low_energy_markers)
            for signal in mood_signals
        ):
            return "low_energy"
        if len(very_recent) >= 3 or any(marker in latest_content for marker in busy_markers):
            return "busy"
        if not inbound_recent:
            return "low_energy" if local_hour >= 22 or local_hour < 7 else "available"
        last_message = inbound_recent[0]
        if last_message.message_timestamp <= now - timedelta(minutes=25):
            return "available"
        return "available" if 9 <= local_hour < 20 else "low_energy"

    def _moment_suppression(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        moment_state: str,
        now: datetime,
    ) -> tuple[str, str, datetime] | None:
        if moment_state == "high_focus" and candidate.category in {"project_nudge", "routine"}:
            return (
                "moment_state_high_focus",
                "Momento atual sugere foco alto; melhor nao interromper com esse tipo de nudge.",
                now + timedelta(minutes=50),
            )
        if moment_state == "busy" and candidate.category == "project_nudge":
            payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
            if not payload.get("recent_signal"):
                return (
                    "moment_state_busy_project",
                    "Momento atual parece corrido; nudge de projeto sem urgencia concreta foi adiado.",
                    now + timedelta(minutes=40),
                )
        if moment_state == "busy" and candidate.category == "routine":
            return (
                "moment_state_busy",
                "Momento atual parece corrido demais para nudge de rotina.",
                now + timedelta(minutes=35),
            )
        return None

    def _recent_owner_activity_suppression(
        self,
        *,
        category: str,
        now: datetime,
        recent_owner_inbound: bool,
        can_bypass: bool,
    ) -> tuple[str, str, datetime] | None:
        if not recent_owner_inbound or can_bypass:
            return None
        delay_minutes = 8 if category == "followup" else 12
        return (
            "active_conversation",
            "O dono ainda está ativo na conversa agora; melhor esperar um respiro antes de um novo nudge.",
            now + timedelta(minutes=delay_minutes),
        )

    def _has_owner_inbound_after_delivery(
        self,
        *,
        delivery: ProactiveDeliveryLogRecord,
    ) -> bool:
        owner_phone = self._resolve_owner_phone()
        if not owner_phone:
            return False
        threshold = delivery.sent_at or delivery.created_at
        messages = self.store.list_whatsapp_agent_messages_for_contact(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            limit=10,
        )
        return any(
            message.direction == "inbound" and message.message_timestamp > threshold
            for message in messages
        )

    def _unanswered_previous_nudge_suppression(
        self,
        *,
        category: str,
        now: datetime,
        last_sent_delivery: ProactiveDeliveryLogRecord | None,
        can_bypass: bool,
    ) -> tuple[str, str, datetime] | None:
        if can_bypass or last_sent_delivery is None:
            return None
        if last_sent_delivery.created_at < now - timedelta(minutes=UNANSWERED_PROACTIVE_WINDOW_MINUTES):
            return None
        if self._has_owner_inbound_after_delivery(delivery=last_sent_delivery):
            return None
        return (
            "unanswered_previous_nudge",
            "Ainda existe um nudge recente sem resposta do dono; melhor nao empilhar outro agora.",
            now + timedelta(minutes=30 if category == "followup" else 45),
        )

    def _min_interval_suppression(
        self,
        *,
        category: str,
        prefs: ProactivePreferencesRecord,
        now: datetime,
        last_sent_delivery: ProactiveDeliveryLogRecord | None,
        can_bypass: bool,
    ) -> tuple[str, str, datetime] | None:
        if last_sent_delivery is None:
            return None
        effective_interval = prefs.min_interval_minutes
        if prefs.intensity == "high":
            effective_interval = max(15, int(round(effective_interval * 0.5)))
        elif prefs.intensity == "conservative":
            effective_interval = min(240, int(round(effective_interval * 1.2)))
        if prefs.presence_mode == "active":
            effective_interval = max(15, int(round(effective_interval * 0.85)))
        if last_sent_delivery.created_at < now - timedelta(minutes=effective_interval):
            return None

        if can_bypass:
            return None

        remaining_minutes = max(
            10,
            int(
                (
                    (last_sent_delivery.created_at + timedelta(minutes=effective_interval)) - now
                ).total_seconds()
                // 60
            ),
        )
        return (
            "min_interval_active",
            f"A última iniciativa foi recente demais; esse nudge volta a competir em cerca de {remaining_minutes} min.",
            now + timedelta(minutes=min(remaining_minutes, max(20, effective_interval // 2))),
        )

    async def _send_unsolicited_message(
        self,
        *,
        category: str,
        message_text: str,
        reason_code: str,
        reason_text: str,
        score: int,
        candidate_id: str | None,
        now: datetime,
    ) -> bool:
        owner_target = await self._resolve_owner_chat_target()
        if not owner_target:
            self.store.create_proactive_delivery_log(
                user_id=self.settings.default_user_id,
                candidate_id=candidate_id,
                category=category,
                decision="failed",
                score=score,
                reason_code="owner_target_missing",
                reason_text="Número do dono não localizado.",
                message_text=message_text,
                message_id=None,
                sent_at=None,
            )
            return False

        owner_phone = self._resolve_owner_phone() or self.store.normalize_contact_phone(owner_target)
        if not owner_phone:
            return False

        thread = self.store.get_or_create_whatsapp_agent_thread(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            chat_jid=owner_target,
            contact_name="Usuario",
            created_at=now,
        )
        session, _ = self.store.resolve_whatsapp_agent_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=thread.contact_phone,
            chat_jid=owner_target,
            activity_at=now,
            idle_timeout_minutes=max(60, self.settings.whatsapp_agent_idle_timeout_minutes),
        )

        outbound_record = self.store.append_whatsapp_agent_message(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            direction="outbound",
            role="assistant",
            session_id=session.id,
            content=message_text,
            message_timestamp=now,
            contact_phone=thread.contact_phone,
            chat_jid=owner_target,
            processing_status="sending",
            learning_status="not_applicable",
            metadata={
                "generated_by": "proactive_assistant",
                "proactive_category": category,
                "proactive_candidate_id": candidate_id,
                "proactive_unsolicited": True,
                "proactive_reason_code": reason_code,
            },
            created_at=now,
        )
        try:
            send_result = await self.agent_gateway.send_text_message(chat_jid=owner_target, message_text=message_text)
        except Exception as send_exc:
            logger.warning("proactive_send_failed detail=%s", send_exc)
            self.store.update_whatsapp_agent_message(
                message_id=outbound_record.id,
                send_status="failed",
                processing_status="failed_send",
                error_text=str(send_exc),
            )
            self.store.create_proactive_delivery_log(
                user_id=self.settings.default_user_id,
                candidate_id=candidate_id,
                category=category,
                decision="failed",
                score=score,
                reason_code=reason_code,
                reason_text=reason_text,
                message_text=message_text,
                message_id=None,
                sent_at=None,
            )
            return False

        sent_at = send_result.timestamp or now
        self.store.update_whatsapp_agent_message(
            message_id=outbound_record.id,
            send_status="sent",
            processing_status="sent",
            whatsapp_message_id=send_result.message_id,
            message_timestamp=sent_at,
        )
        self.store.update_whatsapp_agent_thread(
            thread_id=thread.id,
            chat_jid=owner_target,
            status="active",
            last_outbound_at=sent_at,
            last_message_at=sent_at,
            last_error_at=None,
            last_error_text=None,
        )
        self.store.update_whatsapp_agent_session(
            session_id=session.id,
            last_activity_at=sent_at,
            updated_at=sent_at,
        )
        self.store.create_proactive_delivery_log(
            user_id=self.settings.default_user_id,
            candidate_id=candidate_id,
            category=category,
            decision="sent",
            score=score,
            reason_code=reason_code,
            reason_text=reason_text,
            message_text=message_text,
            message_id=outbound_record.id,
            sent_at=sent_at,
        )
        return True

    def _daily_send_budget_exhausted(self, *, prefs: ProactivePreferencesRecord, now: datetime) -> bool:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        sent_count = self.store.count_proactive_deliveries_since(
            user_id=self.settings.default_user_id,
            since=day_start,
            decisions=["sent"],
        )
        return sent_count >= prefs.max_unsolicited_per_day

    def _min_interval_active(self, *, prefs: ProactivePreferencesRecord, now: datetime) -> bool:
        deliveries = self.store.list_recent_proactive_deliveries(
            user_id=self.settings.default_user_id,
            limit=1,
            decisions=["sent"],
        )
        if not deliveries:
            return False
        last_delivery = deliveries[0]
        return last_delivery.created_at >= now - timedelta(minutes=prefs.min_interval_minutes)

    def _recent_owner_activity(self, *, now: datetime) -> bool:
        owner_phone = self._resolve_owner_phone()
        if not owner_phone:
            return False
        messages = self.store.list_whatsapp_agent_messages_for_contact(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            limit=8,
        )
        threshold = now - timedelta(minutes=RECENT_OWNER_ACTIVITY_SUPPRESSION_MINUTES)
        return any(message.message_timestamp >= threshold for message in messages)

    def _recent_owner_inbound_activity(self, *, now: datetime) -> bool:
        owner_phone = self._resolve_owner_phone()
        if not owner_phone:
            return False
        messages = self.store.list_whatsapp_agent_messages_for_contact(
            user_id=self.settings.default_user_id,
            contact_phone=owner_phone,
            limit=8,
        )
        threshold = now - timedelta(minutes=RECENT_OWNER_ACTIVITY_SUPPRESSION_MINUTES)
        return any(
            message.direction == "inbound" and message.message_timestamp >= threshold
            for message in messages
        )

    def _digest_is_due(self, *, local_now: datetime, last_sent_at: datetime | None, target_time: str) -> bool:
        digest_time = self._parse_local_time(target_time)
        if local_now.time() < digest_time:
            return False
        if last_sent_at is None:
            return True
        return last_sent_at.astimezone(DEFAULT_TIMEZONE).date() < local_now.date()

    def _build_morning_digest(self, *, now: datetime) -> tuple[dict[str, Any], str]:
        start_of_day = now.astimezone(DEFAULT_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        end_of_day = start_of_day + timedelta(days=1)
        today_events = [
            event
            for event in self.store.list_agenda_events(user_id=self.settings.default_user_id, limit=20, starts_after=start_of_day)
            if event.inicio < end_of_day
        ][:3]
        open_candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=12,
            statuses=["suggested", "confirmed"],
        )
        important = self.store.list_important_messages(self.settings.default_user_id, limit=2)

        facts: list[str] = []
        if today_events:
            event_chunks = [
                f"{event.titulo} às {event.inicio.astimezone(DEFAULT_TIMEZONE).strftime('%H:%M')}"
                for event in today_events
            ]
            facts.append("Agenda: " + "; ".join(event_chunks))
        if open_candidates:
            top_candidates = [
                candidate.title.replace("Pendente sugerida: ", "").strip()
                for candidate in open_candidates[:2]
            ]
            facts.append("Em radar: " + "; ".join(top_candidates))
        if important:
            facts.append("Importante recente: " + "; ".join(item.importance_reason[:80] for item in important[:1]))
        top_project = self._select_project_for_digest()
        if top_project is not None:
            project_name, next_step = top_project
            facts.append(f"Projeto para destravar: {project_name[:72]}")
            facts.append(f"Proximo passo mais claro: {next_step[:88]}")
        if not facts:
            return {}, ""
        signature = self._signature_for(facts)
        return {
            "title": "Radar da manha",
            "summary": "Abertura curta do dia com agenda, prioridades e foco.",
            "facts": facts,
            "signature": signature,
        }, signature

    def _build_night_digest(self, *, now: datetime) -> tuple[dict[str, Any], str]:
        tomorrow_start_local = now.astimezone(DEFAULT_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        tomorrow_end_local = tomorrow_start_local + timedelta(days=1)
        tomorrow_start = tomorrow_start_local.astimezone(UTC)
        tomorrow_end = tomorrow_end_local.astimezone(UTC)
        tomorrow_events = [
            event
            for event in self.store.list_agenda_events(user_id=self.settings.default_user_id, limit=20, starts_after=tomorrow_start)
            if event.inicio < tomorrow_end
        ][:3]
        open_candidates = self.store.list_proactive_candidates(
            user_id=self.settings.default_user_id,
            limit=12,
            statuses=["suggested", "confirmed"],
        )
        facts: list[str] = []
        if open_candidates:
            pending_titles = [
                candidate.title.replace("Pendente sugerida: ", "").strip()
                for candidate in open_candidates[:3]
            ]
            facts.append("Ainda em aberto: " + "; ".join(pending_titles))
        if tomorrow_events:
            facts.append(
                "Amanhã cedo: "
                + "; ".join(
                    f"{event.titulo} às {event.inicio.astimezone(DEFAULT_TIMEZONE).strftime('%H:%M')}"
                    for event in tomorrow_events
                )
            )
        top_project = self._select_project_for_digest()
        if top_project is not None:
            project_name, next_step = top_project
            facts.append(f"Projeto mais vivo agora: {project_name[:72]}")
            facts.append(f"Proximo passo mais claro: {next_step[:88]}")
        if not facts:
            return {}, ""
        signature = self._signature_for(facts)
        return {
            "title": "Fechamento do dia",
            "summary": "Fechamento curto com pendencias e foco para amanha.",
            "facts": facts,
            "signature": signature,
        }, signature

    def _create_or_refresh_candidate(
        self,
        *,
        active_candidates: list[ProactiveCandidateRecord],
        candidate_data: dict[str, Any],
    ) -> ProactiveCandidateRecord:
        payload = candidate_data.get("payload_json") or {}
        dedupe_key = str(payload.get("dedupe_key") or "").strip()
        for existing in active_candidates:
            existing_payload = existing.payload_json if isinstance(existing.payload_json, dict) else {}
            if dedupe_key and dedupe_key == str(existing_payload.get("dedupe_key") or "").strip():
                updated = self.store.update_proactive_candidate(
                    candidate_id=existing.id,
                    summary=str(candidate_data.get("summary") or existing.summary),
                    confidence=max(existing.confidence, int(candidate_data.get("confidence") or existing.confidence)),
                    priority=max(existing.priority, int(candidate_data.get("priority") or existing.priority)),
                    due_at=candidate_data.get("due_at") if isinstance(candidate_data.get("due_at"), datetime) else existing.due_at,
                    cooldown_until=candidate_data.get("cooldown_until") if isinstance(candidate_data.get("cooldown_until"), datetime) else existing.cooldown_until,
                    payload_json={**existing_payload, **payload},
                )
                return updated or existing

        return self.store.create_proactive_candidate(
            user_id=self.settings.default_user_id,
            category=str(candidate_data.get("category") or "followup"),
            status=str(candidate_data.get("status") or "suggested"),
            source_message_id=str(candidate_data.get("source_message_id") or "") or None,
            source_kind=str(candidate_data.get("source_kind") or "heuristic"),
            thread_id=str(candidate_data.get("thread_id") or "") or None,
            contact_phone=str(candidate_data.get("contact_phone") or "") or None,
            chat_jid=str(candidate_data.get("chat_jid") or "") or None,
            title=str(candidate_data.get("title") or "Sugestão proativa"),
            summary=str(candidate_data.get("summary") or ""),
            confidence=int(candidate_data.get("confidence") or 0),
            priority=int(candidate_data.get("priority") or 0),
            due_at=candidate_data.get("due_at") if isinstance(candidate_data.get("due_at"), datetime) else None,
            cooldown_until=candidate_data.get("cooldown_until") if isinstance(candidate_data.get("cooldown_until"), datetime) else None,
            last_nudged_at=None,
            payload_json=payload,
        )

    def _resolve_followup_due_at(self, *, message_text: str, occurred_at: datetime) -> datetime:
        local_occurred = occurred_at.astimezone(DEFAULT_TIMEZONE)
        relative_match = RELATIVE_DELAY_REGEX.search(message_text)
        if relative_match:
            amount_text = str(relative_match.group("amount") or "").strip().lower()
            unit = str(relative_match.group("unit") or "").strip().lower()
            amount = 1
            if amount_text == "meia":
                amount = 30
                unit = "min"
            elif amount_text not in {"um", "uma"}:
                try:
                    amount = max(1, int(amount_text))
                except ValueError:
                    amount = 1
            if unit.startswith("min"):
                return occurred_at + timedelta(minutes=amount)
            if unit.startswith("h"):
                return occurred_at + timedelta(hours=amount)
            return occurred_at + timedelta(days=amount)
        if "amanha" in message_text or "amanhã" in message_text:
            target_hour = 10
            if "cedo" in message_text or "manh" in message_text:
                target_hour = 9
            elif "tarde" in message_text:
                target_hour = 15
            elif "noite" in message_text:
                target_hour = 19
            return datetime.combine(
                local_occurred.date() + timedelta(days=1),
                time(hour=target_hour, minute=0),
                tzinfo=DEFAULT_TIMEZONE,
            ).astimezone(UTC)
        if "hoje" in message_text:
            return occurred_at + timedelta(hours=3)
        weekday_due = self._resolve_followup_weekday_due_at(message_text=message_text, occurred_at=occurred_at)
        if weekday_due is not None:
            return weekday_due
        if "mais tarde" in message_text or "depois" in message_text:
            return occurred_at + timedelta(hours=4)
        return occurred_at + timedelta(hours=6)

    def _extract_followup_task(self, message_text: str) -> str:
        compact = " ".join(message_text.split()).strip()
        reminder_match = REMINDER_REQUEST_REGEX.search(compact)
        if reminder_match:
            compact = str(reminder_match.group("task") or "").strip(" .,:;") or compact
        lowered = compact.lower()
        for keyword in FOLLOWUP_KEYWORDS:
            marker = f"{keyword} "
            index = lowered.find(marker)
            if index >= 0:
                compact = compact[index:].strip(" .,:;")
                break
        compact = re.sub(
            r"^(?:preciso(?:\s+de)?|tenho\s+que|tenho\s+de|nao\s+esquecer(?:\s+de)?|não\s+esquecer(?:\s+de)?|vou)\s+",
            "",
            compact,
            flags=re.IGNORECASE,
        ).strip(" .,:;")
        compact = re.sub(r"\s+", " ", compact).strip()
        return compact[:160]

    def _resolve_followup_weekday_due_at(self, *, message_text: str, occurred_at: datetime) -> datetime | None:
        weekdays = {
            "segunda": 0,
            "terca": 1,
            "terça": 1,
            "quarta": 2,
            "quinta": 3,
            "sexta": 4,
            "sabado": 5,
            "sábado": 5,
            "domingo": 6,
        }
        lowered = message_text.lower()
        target_hour = 10
        if "cedo" in lowered or "manh" in lowered:
            target_hour = 9
        elif "tarde" in lowered:
            target_hour = 15
        elif "noite" in lowered:
            target_hour = 19
        local_occurred = occurred_at.astimezone(DEFAULT_TIMEZONE)
        for label, weekday_index in weekdays.items():
            if label not in lowered:
                continue
            days_ahead = (weekday_index - local_occurred.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            if "proxim" in lowered or "próxim" in lowered:
                days_ahead = days_ahead if days_ahead > 0 else 7
            target_date = local_occurred.date() + timedelta(days=days_ahead)
            return datetime.combine(target_date, time(hour=target_hour, minute=0), tzinfo=DEFAULT_TIMEZONE).astimezone(UTC)
        return None

    def _dedupe_token(self, value: str) -> str:
        compact = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return compact[:72] or "generic"

    def _signature_for(self, lines: list[str]) -> str:
        return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()

    def _select_project_for_digest(self) -> tuple[str, str] | None:
        projects = [
            project
            for project in self.store.list_project_memories(self.settings.default_user_id, limit=6)
            if project.project_name.strip() and project.completion_source != "manual"
        ]
        if not projects:
            return None
        for project in projects:
            next_step = (project.next_steps[0] if project.next_steps else "").strip()
            if next_step:
                return project.project_name, next_step
        project = projects[0]
        fallback = project.what_is_being_built.strip() or project.summary.strip()
        if not fallback:
            return None
        return project.project_name, self._summarize_text(fallback, 88)

    def _parse_local_time(self, value: str) -> time:
        normalized = (value or "08:30").strip()
        try:
            hour_str, minute_str = normalized.split(":", 1)
            return time(hour=max(0, min(23, int(hour_str))), minute=max(0, min(59, int(minute_str))))
        except Exception:
            return time(hour=8, minute=30)

    def _is_quiet_time(self, local_now: datetime, prefs: ProactivePreferencesRecord) -> bool:
        start = self._parse_local_time(prefs.quiet_hours_start)
        end = self._parse_local_time(prefs.quiet_hours_end)
        now_time = local_now.time()
        if start == end:
            return False
        if start < end:
            return start <= now_time < end
        return now_time >= start or now_time < end

    def _resolve_owner_phone(self) -> str | None:
        recent_thread = self._select_recent_owner_thread()
        if recent_thread is not None:
            recent_phone = self.store.normalize_contact_phone(recent_thread.contact_phone or recent_thread.chat_jid)
            if recent_phone:
                return recent_phone
        return self.store.normalize_contact_phone(
            self.store.get_whatsapp_session_owner_phone(session_id=f"{self.settings.default_user_id}:observer")
        )

    async def _resolve_owner_chat_target(self) -> str | None:
        recent_target = self._resolve_recent_owner_chat_target()
        if recent_target:
            return recent_target
        try:
            observer_target = self._normalize_chat_target(
                (await self.observer_gateway.get_observer_status(refresh_qr=False)).owner_number
            )
        except Exception:
            observer_target = None
        if observer_target:
            return observer_target
        return self._normalize_chat_target(self._resolve_owner_phone())

    def _resolve_recent_owner_chat_target(self, *, now: datetime | None = None) -> str | None:
        recent_thread = self._select_recent_owner_thread(now=now)
        if recent_thread is None:
            return None
        if recent_thread.chat_jid and self.store.is_direct_chat_jid(recent_thread.chat_jid):
            return recent_thread.chat_jid
        return self._normalize_chat_target(recent_thread.contact_phone)

    def _select_recent_owner_thread(self, *, now: datetime | None = None) -> WhatsAppAgentThreadRecord | None:
        reference_now = now or datetime.now(UTC)
        recent_cutoff = reference_now - timedelta(days=RECENT_OWNER_THREAD_LOOKBACK_DAYS)
        fallback_thread: WhatsAppAgentThreadRecord | None = None
        for thread in self.store.list_whatsapp_agent_threads(user_id=self.settings.default_user_id, limit=8):
            if not self.store.normalize_contact_phone(thread.contact_phone or thread.chat_jid):
                continue
            activity_at = thread.last_inbound_at or thread.last_outbound_at or thread.last_message_at or thread.updated_at
            if fallback_thread is None:
                fallback_thread = thread
            if activity_at >= recent_cutoff:
                return thread
        return fallback_thread

    def _normalize_chat_target(self, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if "@" in text:
            return text
        digits = "".join(char for char in text if char.isdigit())
        if len(digits) >= 12 and digits.startswith("55"):
            digits = digits[2:]
        if len(digits) > 11:
            digits = digits[-11:]
        if 8 <= len(digits) <= 11:
            return f"{digits}@s.whatsapp.net"
        return None

    def _last_sent_delivery(self) -> ProactiveDeliveryLogRecord | None:
        deliveries = self.store.list_recent_proactive_deliveries(
            user_id=self.settings.default_user_id,
            limit=1,
            decisions=["sent"],
        )
        return deliveries[0] if deliveries else None
