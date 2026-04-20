from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
import hashlib
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.deepseek_service import DeepSeekService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.supabase_store import (
    ImportantMessageRecord,
    ProjectMemoryRecord,
    ProactiveCandidateRecord,
    ProactiveDeliveryLogRecord,
    ProactivePreferencesRecord,
    SupabaseStore,
    WhatsAppAgentThreadRecord,
)

DEFAULT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
PROACTIVE_LOOP_INTERVAL_SECONDS = 45
RECENT_REPLY_WINDOW_HOURS = 36
RECENT_PROJECT_NUDGE_HOURS = 14
RECENT_DIGEST_ACTIVITY_MINUTES = 25
IMPORTANT_MESSAGE_CANDIDATE_HOURS = 96
PROJECT_STALE_NUDGE_HOURS = 12
RECENT_OWNER_THREAD_LOOKBACK_DAYS = 14
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
logger = logging.getLogger("auracore.proactive_assistant")


@dataclass(slots=True)
class ProactiveReplyOutcome:
    handled: bool = False
    assistant_reply: str | None = None
    candidate: ProactiveCandidateRecord | None = None


class ProactiveAssistantService:
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
        if self._recent_owner_activity(now=now):
            return
        digest_state = self.store.get_proactive_digest_state(user_id=self.settings.default_user_id)

        if prefs.morning_digest_enabled and self._digest_is_due(local_now=local_now, last_sent_at=digest_state.last_morning_digest_at, target_time=prefs.morning_digest_time):
            text, signature = self._build_morning_digest(now=now)
            if text and signature != digest_state.last_morning_digest_signature:
                sent = await self._send_unsolicited_message(
                    category="morning_digest",
                    message_text=text,
                    reason_code="scheduled_digest",
                    reason_text="Resumo curto da manhã.",
                    score=84,
                    candidate_id=None,
                    now=now,
                )
                if sent:
                    self.store.update_proactive_digest_state(
                        user_id=self.settings.default_user_id,
                        last_morning_digest_at=now,
                        last_morning_digest_signature=signature,
                    )

        if prefs.night_digest_enabled and self._digest_is_due(local_now=local_now, last_sent_at=digest_state.last_night_digest_at, target_time=prefs.night_digest_time):
            text, signature = self._build_night_digest(now=now)
            if text and signature != digest_state.last_night_digest_signature:
                sent = await self._send_unsolicited_message(
                    category="night_digest",
                    message_text=text,
                    reason_code="scheduled_digest",
                    reason_text="Fechamento curto do dia.",
                    score=80,
                    candidate_id=None,
                    now=now,
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
        last_sent_delivery = self._last_sent_delivery()
        logger.info("proactive_moment_state user_id=%s moment_state=%s", self.settings.default_user_id, moment_state)

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

            interval_suppression = self._min_interval_suppression(
                candidate=candidate,
                prefs=prefs,
                now=now,
                last_sent_delivery=last_sent_delivery,
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

        message_text = self._render_candidate_message(candidate=best_candidate)
        if not message_text:
            return

        sent = await self._send_unsolicited_message(
            category=best_candidate.category,
            message_text=message_text,
            reason_code="candidate_due",
            reason_text=f"{best_candidate.summary or best_candidate.title} [moment={moment_state}]",
            score=best_score,
            candidate_id=best_candidate.id,
            now=now,
        )
        if not sent:
            self.store.update_proactive_candidate(
                candidate_id=best_candidate.id,
                cooldown_until=now + timedelta(minutes=45),
            )
            return

        next_status = "sent"
        next_cooldown = now + timedelta(hours=12)
        if best_candidate.status == "confirmed":
            next_cooldown = now + timedelta(hours=18)
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
            score += 14
        if candidate.category == "project_nudge" and payload.get("recent_signal"):
            score += 10
        if candidate.category == "routine":
            score -= 2
        if moment_state == "high_focus":
            score -= 14
        elif moment_state == "available":
            score += 10
        elif moment_state == "low_energy":
            if candidate.category == "routine":
                score += 6
            if candidate.category == "project_nudge":
                score -= 2
        elif moment_state == "busy":
            score -= 4
        if prefs.intensity == "high":
            if candidate.category in {"followup", "project_nudge"}:
                score += 10
            elif candidate.category == "routine":
                score += 5
        elif prefs.intensity == "conservative":
            if candidate.category == "routine":
                score -= 10
            elif candidate.category == "project_nudge":
                score -= 4
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
            base -= 10
        elif prefs.intensity == "conservative":
            base += 8
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

    def _render_candidate_message(self, *, candidate: ProactiveCandidateRecord) -> str:
        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        if candidate.category == "followup":
            task_text = str(payload.get("task_text") or candidate.title).strip()
            important_reason = str(payload.get("source_reason") or "").strip()
            source_excerpt = str(payload.get("source_excerpt") or "").strip()
            important_source = bool(payload.get("important_source"))
            if important_source:
                intro = important_reason[:140] or task_text[:140]
                support = ""
                if source_excerpt:
                    support = f" Sinal que ficou no radar: {source_excerpt[:110]}."
                if candidate.status == "confirmed":
                    return (
                        f"Isso continua importante e ainda parece aberto: {intro}."
                        f"{support} Quer que eu te cobre isso depois ou destrave agora?"
                    )
                return (
                    f"Tem um ponto importante em aberto: {intro}."
                    f"{support} Quer que eu te organize o próximo passo agora?"
                )
            if candidate.status == "confirmed":
                return (
                    f"Isso continua aberto: {task_text[:140]}. "
                    "Vale resolver agora ou quer que eu só te lembre mais tarde?"
                )
            return (
                f"Você puxou isso como pendência: {task_text[:140]}. "
                "Quer que eu te ajude a destravar agora ou só deixe no radar?"
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
            action_text = ""
            if suggested_actions:
                action_text = " Ações concretas agora: " + " | ".join(
                    f"{index + 1}) {action[:80]}"
                    for index, action in enumerate(suggested_actions[:2])
                )
            reason_text = f" Sinal de prioridade: {project_reason[:100]}." if project_reason else ""
            if next_step:
                return (
                    f"Projeto em radar: {project_name[:100]}. "
                    f"O próximo passo mais claro parece ser {next_step[:120]}."
                    f"{reason_text}"
                    f"{action_text} Quer que eu te deixe um plano curto?"
                )
            if action_text:
                return (
                    f"Projeto em radar: {project_name[:100]}.{reason_text}"
                    f"{action_text} Quer que eu te organize uma delas?"
                )
            return f"Vale revisar {project_name[:100]} agora ou eu te monto um próximo passo enxuto?"
        if candidate.category == "routine":
            suggestion = str(payload.get("suggestion") or "Vale reorganizar o próximo bloco com mais leveza.").strip()
            return f"{candidate.summary[:140]} {suggestion[:140]}"
        if candidate.category == "agenda_followup":
            return f"{candidate.summary[:180]} Quer que eu organize isso agora?"
        return candidate.summary[:220]

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
            if created >= 3:
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
            if project.next_steps:
                score += 24
            if project.what_is_being_built:
                score += 14
            if project.built_for:
                score += 8
            if project.evidence:
                score += min(10, len(project.evidence) * 3)
            if any(marker in status for marker in ("ativo", "andamento", "fazendo", "aberto", "execu")):
                score += 14
            if any(marker in status for marker in ("concl", "finaliz", "done", "encerr")):
                score -= 18
            pivot = project.last_seen_at or project.updated_at
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
                now + timedelta(minutes=90),
            )
        if moment_state == "busy" and candidate.category == "project_nudge":
            payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
            if not payload.get("recent_signal"):
                return (
                    "moment_state_busy_project",
                    "Momento atual parece corrido; nudge de projeto sem urgencia concreta foi adiado.",
                    now + timedelta(minutes=75),
                )
        if moment_state == "busy" and candidate.category == "routine":
            return (
                "moment_state_busy",
                "Momento atual parece corrido demais para nudge de rotina.",
                now + timedelta(minutes=60),
            )
        return None

    def _min_interval_suppression(
        self,
        *,
        candidate: ProactiveCandidateRecord,
        prefs: ProactivePreferencesRecord,
        now: datetime,
        last_sent_delivery: ProactiveDeliveryLogRecord | None,
    ) -> tuple[str, str, datetime] | None:
        if last_sent_delivery is None:
            return None
        effective_interval = prefs.min_interval_minutes
        if prefs.intensity == "high":
            effective_interval = max(20, int(round(effective_interval * 0.65)))
        elif prefs.intensity == "conservative":
            effective_interval = min(240, int(round(effective_interval * 1.2)))
        if last_sent_delivery.created_at < now - timedelta(minutes=effective_interval):
            return None

        payload = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
        can_bypass = (
            candidate.status == "confirmed"
            or bool(payload.get("important_source"))
            or candidate.priority >= 88
            or (
                candidate.category == "project_nudge"
                and bool(payload.get("recent_signal"))
                and prefs.intensity != "conservative"
            )
        )
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
        threshold = now - timedelta(minutes=RECENT_DIGEST_ACTIVITY_MINUTES)
        return any(message.message_timestamp >= threshold for message in messages)

    def _digest_is_due(self, *, local_now: datetime, last_sent_at: datetime | None, target_time: str) -> bool:
        digest_time = self._parse_local_time(target_time)
        if local_now.time() < digest_time:
            return False
        if last_sent_at is None:
            return True
        return last_sent_at.astimezone(DEFAULT_TIMEZONE).date() < local_now.date()

    def _build_morning_digest(self, *, now: datetime) -> tuple[str, str]:
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

        lines = ["Bom dia. Radar curto de agora:"]
        if today_events:
            event_chunks = [
                f"{event.titulo} às {event.inicio.astimezone(DEFAULT_TIMEZONE).strftime('%H:%M')}"
                for event in today_events
            ]
            lines.append("Agenda: " + "; ".join(event_chunks))
        if open_candidates:
            top_candidates = [
                candidate.title.replace("Pendente sugerida: ", "").strip()
                for candidate in open_candidates[:2]
            ]
            lines.append("Pendências em radar: " + "; ".join(top_candidates))
        if important:
            lines.append("Importante recente: " + "; ".join(item.importance_reason[:80] for item in important[:1]))
        top_project = self._select_project_for_digest()
        if top_project is not None:
            project_name, next_step = top_project
            lines.append(f"Projeto para destravar: {project_name[:72]} -> {next_step[:88]}")
        if len(lines) == 1:
            return "", ""
        signature = self._signature_for(lines)
        return "\n".join(lines), signature

    def _build_night_digest(self, *, now: datetime) -> tuple[str, str]:
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
        lines = ["Fechamento curto do dia:"]
        if open_candidates:
            pending_titles = [
                candidate.title.replace("Pendente sugerida: ", "").strip()
                for candidate in open_candidates[:3]
            ]
            lines.append("Ainda em aberto: " + "; ".join(pending_titles))
        if tomorrow_events:
            lines.append(
                "Amanhã cedo: "
                + "; ".join(
                    f"{event.titulo} às {event.inicio.astimezone(DEFAULT_TIMEZONE).strftime('%H:%M')}"
                    for event in tomorrow_events
                )
            )
        top_project = self._select_project_for_digest()
        if top_project is not None:
            project_name, next_step = top_project
            lines.append(f"Projeto mais vivo agora: {project_name[:72]} -> {next_step[:88]}")
        if len(lines) == 1:
            return "", ""
        signature = self._signature_for(lines)
        return "\n".join(lines), signature

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
        if "amanha" in message_text or "amanhã" in message_text:
            return datetime.combine(local_occurred.date() + timedelta(days=1), time(hour=10, minute=0), tzinfo=DEFAULT_TIMEZONE).astimezone(UTC)
        if "hoje" in message_text:
            return occurred_at + timedelta(hours=3)
        if "mais tarde" in message_text or "depois" in message_text:
            return occurred_at + timedelta(hours=4)
        return occurred_at + timedelta(hours=6)

    def _extract_followup_task(self, message_text: str) -> str:
        compact = " ".join(message_text.split()).strip()
        lowered = compact.lower()
        for keyword in FOLLOWUP_KEYWORDS:
            marker = f"{keyword} "
            index = lowered.find(marker)
            if index >= 0:
                return compact[index:].strip(" .,:;")
        return compact[:160]

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
