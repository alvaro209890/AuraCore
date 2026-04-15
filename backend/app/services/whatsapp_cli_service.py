from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
import logging
import shlex
import subprocess

from app.config import Settings
from app.services.deepseek_service import DeepSeekCliAction, DeepSeekCliPlan, DeepSeekService
from app.services.supabase_store import (
    SupabaseStore,
    WhatsAppAgentMessageRecord,
    WhatsAppAgentTerminalSessionRecord,
    WhatsAppAgentThreadRecord,
    WhatsAppAgentThreadSessionRecord,
)

logger = logging.getLogger("auracore.whatsapp_cli")
_UNSET = object()

SENSITIVE_TERMS = {
    "cloudflared",
    "cloudflare",
    "docker",
    "geoserver",
    "kill",
    "pkill",
    "reboot",
    "shutdown",
    "sudo",
    "systemctl",
    "service",
    "tunnel",
    "tunel",
}

DIRECT_TOOL_COMMANDS = {
    "pwd",
    "ls",
    "cd",
    "cat",
    "find",
    "head",
    "tail",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm",
    "rg",
}

SAFE_EXEC_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("git", "status"),
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("git", "rev-parse"),
    ("git", "branch"),
    ("git", "grep"),
    ("git", "ls-files"),
    ("pytest",),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("pnpm", "test"),
    ("pnpm", "build"),
    ("pnpm", "lint"),
    ("yarn", "test"),
    ("yarn", "build"),
    ("yarn", "lint"),
    ("npx", "tsc"),
    ("python", "-m", "py_compile"),
    ("python3", "-m", "py_compile"),
    ("uv", "run", "pytest"),
    ("uv", "run", "python"),
    ("cargo", "test"),
    ("go", "test"),
    ("sed", "-n"),
    ("awk",),
    ("wc",),
    ("stat",),
    ("file",),
)


@dataclass(slots=True)
class CliOutboundMessage:
    text: str
    generated_by: str
    metadata: dict[str, object]


@dataclass(slots=True)
class CliExecutionObservation:
    tool: str
    command: str
    cwd_before: str
    cwd_after: str
    explanation: str
    output: str
    success: bool = True


@dataclass(slots=True)
class CliPendingExecution:
    command_text: str
    cwd: str
    plan: DeepSeekCliPlan
    observations: list[CliExecutionObservation]
    return_mode: str


@dataclass(slots=True)
class WhatsAppCliDispatchResult:
    action: str
    outbound_messages: list[CliOutboundMessage]
    terminal_session: WhatsAppAgentTerminalSessionRecord
    model_run_id: str | None = None


class WhatsAppCliService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        deepseek_service: DeepSeekService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service

    def is_eligible_contact(self, *, contact_phone: str | None) -> bool:
        if self.store.is_whatsapp_agent_admin_contact(
            user_id=self.settings.default_user_id,
            contact_phone=contact_phone,
        ):
            return True
        owner_phone = self.settings.normalized_whatsapp_cli_owner_phone
        return bool(owner_phone and self.store.phone_matches(contact_phone, owner_phone))

    def get_terminal_session_for_thread(self, *, thread_id: str) -> WhatsAppAgentTerminalSessionRecord | None:
        return self.store.get_whatsapp_agent_terminal_session(
            user_id=self.settings.default_user_id,
            thread_id=thread_id,
        )

    async def handle_message(
        self,
        *,
        message_text: str,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        chat_jid: str,
    ) -> WhatsAppCliDispatchResult:
        normalized_text = " ".join(message_text.split()).strip()
        terminal_session = self._ensure_terminal_session(thread=thread, chat_jid=chat_jid)
        control_command = normalized_text.casefold()

        if control_command == "/":
            return WhatsAppCliDispatchResult(
                action="cli_help",
                outbound_messages=[
                    CliOutboundMessage(
                        text=self._build_help_message(cli_mode_enabled=terminal_session.cli_mode_enabled),
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/", "cli_mode_enabled": terminal_session.cli_mode_enabled},
                    )
                ],
                terminal_session=terminal_session,
            )

        if control_command == "/confirmar":
            return await self._confirm_pending_execution(
                inbound_message=inbound_message,
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                terminal_session=terminal_session,
            )

        if control_command == "/cancelar":
            if not self._has_pending_confirmation(terminal_session):
                return WhatsAppCliDispatchResult(
                    action="cli_cancel_noop",
                    outbound_messages=[
                        CliOutboundMessage(
                            text="Nenhuma execução pendente para cancelar.",
                            generated_by="whatsapp_cli_control",
                            metadata={"control_command": "/cancelar"},
                        )
                    ],
                    terminal_session=terminal_session,
                )
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=terminal_session.cli_mode_enabled,
                cwd=terminal_session.cwd,
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
            )
            return WhatsAppCliDispatchResult(
                action="cli_cancelled",
                outbound_messages=[
                    CliOutboundMessage(
                        text="Execução pendente cancelada. Você pode enviar outro comando quando quiser.",
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/cancelar"},
                    )
                ],
                terminal_session=terminal_session,
            )

        if control_command == "/agente":
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=True,
                cwd=self._default_root_cwd(),
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
                last_command_text=None,
                last_command_at=None,
                closed_at=None,
            )
            return WhatsAppCliDispatchResult(
                action="cli_opened",
                outbound_messages=[
                    CliOutboundMessage(
                        text=(
                            "CLI ativada.\n\n"
                            f"Diretorio inicial: `{terminal_session.cwd}`\n"
                            "Comandos diretos rodam como terminal. Pedidos em linguagem natural agora podem explorar o projeto e devolver relatorio automaticamente. "
                            "Uso `/confirmar` e `/cancelar` apenas para acoes sensiveis ou destrutivas."
                        ),
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/agente", "cwd": terminal_session.cwd},
                    )
                ],
                terminal_session=terminal_session,
            )

        if control_command == "/clear":
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=True,
                cwd=self._default_root_cwd(),
                context_version=terminal_session.context_version + 1,
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
                last_command_text=None,
                last_command_at=None,
                closed_at=None,
            )
            return WhatsAppCliDispatchResult(
                action="cli_cleared",
                outbound_messages=[
                    CliOutboundMessage(
                        text=(
                            "Contexto da CLI limpo.\n\n"
                            f"Novo diretorio atual: `{terminal_session.cwd}`\n"
                            f"Versao do contexto: `{terminal_session.context_version}`"
                        ),
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/clear", "cwd": terminal_session.cwd},
                    )
                ],
                terminal_session=terminal_session,
            )

        if control_command == "/fechar":
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=False,
                cwd=terminal_session.cwd,
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
                closed_at=datetime.now(UTC),
            )
            return WhatsAppCliDispatchResult(
                action="cli_closed",
                outbound_messages=[
                    CliOutboundMessage(
                        text="CLI encerrada. Envie `/agente` quando quiser voltar ao modo terminal.",
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/fechar", "cwd": terminal_session.cwd},
                    )
                ],
                terminal_session=terminal_session,
            )

        if not terminal_session.cli_mode_enabled:
            return WhatsAppCliDispatchResult(
                action="cli_inactive",
                outbound_messages=[
                    CliOutboundMessage(
                        text="Modo CLI fechado. Envie `/agente` para abrir o terminal do Cursar no WhatsApp.",
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "inactive_notice"},
                    )
                ],
                terminal_session=terminal_session,
            )

        if self._has_pending_confirmation(terminal_session):
            return WhatsAppCliDispatchResult(
                action="cli_waiting_confirmation",
                outbound_messages=[
                    CliOutboundMessage(
                        text=(
                            "Existe uma execução pendente aguardando confirmação.\n\n"
                            "Envie `/confirmar` para executar ou `/cancelar` para descartar antes de mandar outro comando."
                        ),
                        generated_by="whatsapp_cli_control",
                        metadata={"pending_command_text": terminal_session.pending_command_text or ""},
                    )
                ],
                terminal_session=terminal_session,
            )

        direct_plan = self._try_parse_direct_command(normalized_text)
        return_mode = "raw" if direct_plan is not None else "summary"
        return await self._run_cli_turn(
            command_text=normalized_text,
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            terminal_session=terminal_session,
            initial_plan=direct_plan,
            prior_observations=[],
            return_mode=return_mode,
        )

    async def _run_cli_turn(
        self,
        *,
        command_text: str,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        chat_jid: str,
        terminal_session: WhatsAppAgentTerminalSessionRecord,
        initial_plan: DeepSeekCliPlan | None,
        prior_observations: list[CliExecutionObservation],
        return_mode: str,
    ) -> WhatsAppCliDispatchResult:
        current_cwd = terminal_session.cwd
        latest_model_run_id: str | None = None
        execution_error: str | None = None
        final_text_from_plan: str | None = None
        observations = list(prior_observations)
        session_context = self._build_recent_cli_context(
            thread_id=thread.id,
            exclude_message_id=inbound_message.id,
        )
        plan = initial_plan
        max_rounds = max(1, min(4, self.settings.whatsapp_cli_max_steps))

        for iteration in range(1, max_rounds + 1):
            if plan is None:
                plan, latest_model_run_id, plan_error = await self._request_cli_plan(
                    user_message=command_text,
                    cwd=current_cwd,
                    session_context=session_context,
                    execution_history=self._render_execution_history(observations),
                    iteration=iteration,
                )
                if plan is None:
                    execution_error = plan_error or "DeepSeek indisponível para planejar a execução da CLI."
                    break

            if not plan.actions:
                break

            if self._plan_requires_confirmation(plan=plan, cwd=current_cwd):
                pending_payload = self._serialize_pending_execution(
                    CliPendingExecution(
                        command_text=command_text,
                        cwd=current_cwd,
                        plan=plan,
                        observations=observations,
                        return_mode=return_mode,
                    )
                )
                terminal_session = self._store_terminal_session(
                    thread=thread,
                    session=session,
                    chat_jid=chat_jid,
                    current=terminal_session,
                    cli_mode_enabled=True,
                    cwd=current_cwd,
                    pending_command_text=command_text,
                    pending_plan_json=pending_payload,
                    pending_requested_at=datetime.now(UTC),
                    closed_at=None,
                )
                return WhatsAppCliDispatchResult(
                    action="cli_confirmation_requested",
                    outbound_messages=[
                        CliOutboundMessage(
                            text=self._build_confirmation_message(
                                command_text=command_text,
                                plan=plan,
                                observations=observations,
                            ),
                            generated_by="whatsapp_cli_control",
                            metadata={
                                "phase": "awaiting_confirmation",
                                "cwd": current_cwd,
                                "plan_summary": plan.summary,
                                "model_run_id": latest_model_run_id or "",
                                "source_inbound_message_id": inbound_message.whatsapp_message_id or "",
                            },
                        )
                    ],
                    terminal_session=terminal_session,
                    model_run_id=latest_model_run_id,
                )

            saw_final = False
            executed_any = False
            for action in plan.actions[: max(1, self.settings.whatsapp_cli_max_steps)]:
                if action.tool == "final":
                    saw_final = True
                    final_text_from_plan = action.explanation.strip() or None
                    break

                executed_any = True
                command_label = action.command.strip() or action.path.strip() or action.tool
                cwd_before = current_cwd
                try:
                    result_text, current_cwd = self._run_tool(action=action, cwd=current_cwd)
                    observations.append(
                        CliExecutionObservation(
                            tool=action.tool,
                            command=command_label,
                            cwd_before=cwd_before,
                            cwd_after=current_cwd,
                            explanation=action.explanation.strip(),
                            output=result_text,
                            success=True,
                        )
                    )
                except Exception as error:
                    execution_error = str(error)
                    observations.append(
                        CliExecutionObservation(
                            tool=action.tool,
                            command=command_label,
                            cwd_before=cwd_before,
                            cwd_after=current_cwd,
                            explanation=action.explanation.strip(),
                            output=execution_error,
                            success=False,
                        )
                    )
                    logger.warning(
                        "whatsapp_cli_action_failed thread_id=%s tool=%s command=%s detail=%s",
                        thread.id,
                        action.tool,
                        command_label,
                        execution_error,
                    )
                    break

            if execution_error is not None:
                break

            if saw_final:
                break

            if not executed_any:
                break

            plan = None

        terminal_session = self._store_terminal_session(
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            current=terminal_session,
            cli_mode_enabled=True,
            cwd=current_cwd,
            last_command_text=command_text,
            last_command_at=datetime.now(UTC),
            pending_command_text=None,
            pending_plan_json={},
            pending_requested_at=None,
            closed_at=None,
        )

        outbound_messages: list[CliOutboundMessage]
        if return_mode == "raw":
            outbound_messages = self._build_raw_output_messages(
                observations=observations,
                cwd=current_cwd,
                execution_error=execution_error,
            )
        else:
            summary_text = final_text_from_plan or ""
            if not summary_text:
                summary_text, summary_model_run_id = await self._request_cli_summary(
                    user_message=command_text,
                    cwd=current_cwd,
                    session_context=session_context,
                    execution_history=self._render_execution_history(observations),
                    execution_error=execution_error,
                )
                if summary_model_run_id:
                    latest_model_run_id = summary_model_run_id
            outbound_messages = [
                CliOutboundMessage(
                    text=summary_text,
                    generated_by="whatsapp_cli_final",
                    metadata={
                        "phase": "final",
                        "cwd": current_cwd,
                        "model_run_id": latest_model_run_id or "",
                        "execution_error": execution_error or "",
                    },
                )
            ]

        return WhatsAppCliDispatchResult(
            action="cli_executed" if execution_error is None else "cli_failed",
            outbound_messages=outbound_messages,
            terminal_session=terminal_session,
            model_run_id=latest_model_run_id,
        )

    async def _confirm_pending_execution(
        self,
        *,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        chat_jid: str,
        terminal_session: WhatsAppAgentTerminalSessionRecord,
    ) -> WhatsAppCliDispatchResult:
        if not self._has_pending_confirmation(terminal_session):
            return WhatsAppCliDispatchResult(
                action="cli_confirm_noop",
                outbound_messages=[
                    CliOutboundMessage(
                        text="Nenhuma execução pendente para confirmar.",
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/confirmar"},
                    )
                ],
                terminal_session=terminal_session,
            )

        pending = self._deserialize_pending_execution(
            payload=terminal_session.pending_plan_json,
            fallback_command_text=terminal_session.pending_command_text or terminal_session.last_command_text or "",
            fallback_cwd=terminal_session.cwd,
        )
        if pending is None:
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=True,
                cwd=terminal_session.cwd,
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
            )
            return WhatsAppCliDispatchResult(
                action="cli_confirm_invalid_plan",
                outbound_messages=[
                    CliOutboundMessage(
                        text="O plano pendente ficou inválido e foi descartado. Envie o comando novamente.",
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/confirmar"},
                    )
                ],
                terminal_session=terminal_session,
            )

        terminal_session = self._store_terminal_session(
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            current=terminal_session,
            cli_mode_enabled=True,
            cwd=pending.cwd,
            pending_command_text=None,
            pending_plan_json={},
            pending_requested_at=None,
            closed_at=None,
        )
        return await self._run_cli_turn(
            command_text=pending.command_text,
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            terminal_session=terminal_session,
            initial_plan=pending.plan,
            prior_observations=pending.observations,
            return_mode=pending.return_mode,
        )

    async def _request_cli_plan(
        self,
        *,
        user_message: str,
        cwd: str,
        session_context: str,
        execution_history: str,
        iteration: int,
    ) -> tuple[DeepSeekCliPlan | None, str | None, str | None]:
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        plan: DeepSeekCliPlan | None = None
        error_text: str | None = None
        try:
            plan = await self.deepseek_service.extract_cli_plan(
                user_message=user_message,
                cwd=cwd,
                cli_mode_enabled=True,
                session_context=session_context,
                execution_history=execution_history,
                iteration=iteration,
            )
        except Exception as error:
            error_text = str(error)
            logger.warning("whatsapp_cli_plan_failed detail=%s", error_text)

        model_run = self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=None,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="whatsapp_cli_plan",
            success=plan is not None,
            latency_ms=int((perf_counter() - started_clock) * 1000),
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=error_text,
            created_at=started_at,
        )
        return plan, (model_run.id if model_run else None), error_text

    async def _request_cli_summary(
        self,
        *,
        user_message: str,
        cwd: str,
        session_context: str,
        execution_history: str,
        execution_error: str | None,
    ) -> tuple[str, str | None]:
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        error_text: str | None = None
        summary_text: str
        try:
            summary_text = await self.deepseek_service.summarize_cli_execution(
                user_message=user_message,
                cwd=cwd,
                session_context=session_context,
                execution_history=execution_history,
                execution_error=execution_error,
            )
        except Exception as error:
            error_text = str(error)
            logger.warning("whatsapp_cli_summary_failed detail=%s", error_text)
            if execution_error:
                summary_text = self._format_code_block(f"ERRO\n{execution_error}")
            else:
                summary_text = self._format_code_block(
                    "ERRO\nNao consegui sintetizar a resposta final desta execucao."
                )

        model_run = self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=None,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="whatsapp_cli_summary",
            success=error_text is None,
            latency_ms=int((perf_counter() - started_clock) * 1000),
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=error_text,
            created_at=started_at,
        )
        return summary_text, (model_run.id if model_run else None)

    def _try_parse_direct_command(self, message_text: str) -> DeepSeekCliPlan | None:
        raw = message_text.strip()
        if not raw:
            return None
        try:
            parts = shlex.split(raw)
        except ValueError:
            return None
        if not parts:
            return None

        head = parts[0].strip().lower()
        if head in DIRECT_TOOL_COMMANDS:
            action = DeepSeekCliAction(
                tool=head,
                command=raw,
                explanation="Comando direto do usuario.",
            )
            return DeepSeekCliPlan(summary="Comando direto do usuario.", actions=[action])

        for prefix in SAFE_EXEC_PREFIXES:
            if self._matches_prefix(parts, prefix):
                action = DeepSeekCliAction(
                    tool="exec",
                    command=raw,
                    explanation="Comando shell direto do usuario.",
                )
                return DeepSeekCliPlan(summary="Comando shell direto do usuario.", actions=[action])

        return None

    def _matches_prefix(self, parts: list[str], prefix: tuple[str, ...]) -> bool:
        if len(parts) < len(prefix):
            return False
        return tuple(part.lower() for part in parts[: len(prefix)]) == prefix

    def _build_recent_cli_context(self, *, thread_id: str, exclude_message_id: str | None = None) -> str:
        messages = self.store.list_whatsapp_agent_messages(thread_id=thread_id, limit=14)
        lines: list[str] = []
        for message in reversed(messages):
            if exclude_message_id and message.id == exclude_message_id:
                continue
            metadata = message.metadata if isinstance(message.metadata, dict) else {}
            generated_by = str(metadata.get("generated_by") or "").strip()
            interaction_mode = str(metadata.get("interaction_mode") or "").strip()
            if message.direction == "inbound":
                if interaction_mode != "cli" and not str(message.processing_status).startswith("cli_"):
                    continue
                role = "usuario"
            else:
                if not generated_by.startswith("whatsapp_cli"):
                    continue
                role = "cli"
            text = " ".join(str(message.content or "").split()).strip()
            if not text:
                continue
            lines.append(f"{role}: {self._truncate(text, max_chars=220)}")
        return "\n".join(lines[-8:])

    def _render_execution_history(self, observations: list[CliExecutionObservation]) -> str:
        if not observations:
            return ""
        rendered: list[str] = []
        for index, item in enumerate(observations[-10:], start=1):
            status = "ok" if item.success else "erro"
            rendered.append(
                (
                    f"[{index}] tool={item.tool} status={status}\n"
                    f"cwd_antes={item.cwd_before}\n"
                    f"cwd_depois={item.cwd_after}\n"
                    f"comando={item.command}\n"
                    f"explicacao={item.explanation or '(sem explicacao)'}\n"
                    f"saida=\n{self._truncate(item.output, max_chars=1600)}"
                )
            )
        return "\n\n".join(rendered)

    def _build_raw_output_messages(
        self,
        *,
        observations: list[CliExecutionObservation],
        cwd: str,
        execution_error: str | None,
    ) -> list[CliOutboundMessage]:
        outbound: list[CliOutboundMessage] = []
        for item in observations:
            label = item.command or item.tool
            for chunk in self._format_output_chunks(tool_name=label, content=item.output):
                outbound.append(
                    CliOutboundMessage(
                        text=chunk,
                        generated_by="whatsapp_cli_tool",
                        metadata={
                            "tool": item.tool,
                            "command": item.command,
                            "cwd": item.cwd_after,
                            "success": item.success,
                        },
                    )
                )
        final_text = (
            f"⚠️ Execução encerrada com erro. Diretório atual: {cwd}"
            if execution_error is not None
            else f"✅ Comando finalizado. Diretório atual: {cwd}"
        )
        outbound.append(
            CliOutboundMessage(
                text=final_text,
                generated_by="whatsapp_cli_status",
                metadata={"phase": "finished", "cwd": cwd, "error": execution_error or ""},
            )
        )
        return outbound

    def _serialize_pending_execution(self, pending: CliPendingExecution) -> dict[str, Any]:
        return {
            "kind": "cli_pending_execution",
            "command_text": pending.command_text,
            "cwd": pending.cwd,
            "return_mode": pending.return_mode,
            "plan": pending.plan.model_dump(mode="json"),
            "observations": [
                {
                    "tool": item.tool,
                    "command": item.command,
                    "cwd_before": item.cwd_before,
                    "cwd_after": item.cwd_after,
                    "explanation": item.explanation,
                    "output": item.output,
                    "success": item.success,
                }
                for item in pending.observations
            ],
        }

    def _deserialize_pending_execution(
        self,
        *,
        payload: dict[str, Any],
        fallback_command_text: str,
        fallback_cwd: str,
    ) -> CliPendingExecution | None:
        if not isinstance(payload, dict) or not payload:
            return None

        if "plan" in payload:
            plan = self._deserialize_plan(payload.get("plan"))
            if plan is None:
                return None
            observations: list[CliExecutionObservation] = []
            raw_observations = payload.get("observations")
            if isinstance(raw_observations, list):
                for item in raw_observations:
                    if not isinstance(item, dict):
                        continue
                    observations.append(
                        CliExecutionObservation(
                            tool=str(item.get("tool") or ""),
                            command=str(item.get("command") or ""),
                            cwd_before=str(item.get("cwd_before") or fallback_cwd),
                            cwd_after=str(item.get("cwd_after") or fallback_cwd),
                            explanation=str(item.get("explanation") or ""),
                            output=str(item.get("output") or ""),
                            success=bool(item.get("success", True)),
                        )
                    )
            return CliPendingExecution(
                command_text=str(payload.get("command_text") or fallback_command_text),
                cwd=str(payload.get("cwd") or fallback_cwd),
                plan=plan,
                observations=observations,
                return_mode=str(payload.get("return_mode") or "summary"),
            )

        legacy_plan = self._deserialize_plan(payload)
        if legacy_plan is None:
            return None
        return CliPendingExecution(
            command_text=fallback_command_text,
            cwd=fallback_cwd,
            plan=legacy_plan,
            observations=[],
            return_mode="summary",
        )

    def _plan_requires_confirmation(self, *, plan: DeepSeekCliPlan, cwd: str) -> bool:
        if plan.explicit_sensitive_request:
            return True
        return any(self._action_requires_confirmation(action=action, cwd=cwd) for action in plan.actions if action.tool != "final")

    def _action_requires_confirmation(self, *, action: DeepSeekCliAction, cwd: str) -> bool:
        if self._action_hits_sensitive_area(action):
            return True
        if action.tool == "rm":
            return True
        if action.tool == "exec":
            return self._exec_requires_confirmation(action.command.strip() or action.path.strip())
        if action.tool in {"write", "mkdir", "touch", "cp", "mv"}:
            return self._mutating_path_outside_root(action=action, cwd=cwd)
        return False

    def _exec_requires_confirmation(self, command: str) -> bool:
        raw = command.strip()
        if not raw:
            return True
        lowered = raw.casefold()
        if any(marker in lowered for marker in {"&&", "||", ";", "sudo ", " pkill ", " kill ", "systemctl", "docker ", "cloudflared"}):
            return True
        if any(token in lowered for token in {" rm ", "rm -", "git reset", "git clean", "git checkout --", "git restore ", "reboot", "shutdown"}):
            return True
        try:
            parts = shlex.split(raw)
        except ValueError:
            return True
        if not parts:
            return True
        for prefix in SAFE_EXEC_PREFIXES:
            if self._matches_prefix([part.lower() for part in parts], prefix):
                return False
        return True

    def _mutating_path_outside_root(self, *, action: DeepSeekCliAction, cwd: str) -> bool:
        targets: list[str] = []
        raw = action.command.strip() or action.path.strip()
        try:
            parts = shlex.split(raw) if raw else []
        except ValueError:
            return True

        if action.tool in {"write", "mkdir", "touch"}:
            if raw:
                targets.append(raw)
        elif action.tool in {"cp", "mv"}:
            targets.extend(part for part in parts if part and not part.startswith("-"))

        for target in targets:
            resolved = self._resolve_path(target, cwd=cwd)
            if not self._path_is_within_root(resolved):
                return True
        return False

    def _path_is_within_root(self, path: Path) -> bool:
        root = Path(self.settings.normalized_whatsapp_cli_root).resolve(strict=False)
        try:
            path.resolve(strict=False).relative_to(root)
            return True
        except ValueError:
            return False

    def _ensure_terminal_session(
        self,
        *,
        thread: WhatsAppAgentThreadRecord,
        chat_jid: str,
    ) -> WhatsAppAgentTerminalSessionRecord:
        current = self.store.get_whatsapp_agent_terminal_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
        )
        if current is not None:
            return current
        now = datetime.now(UTC)
        return self.store.upsert_whatsapp_agent_terminal_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=thread.contact_phone,
            chat_jid=chat_jid,
            cli_mode_enabled=False,
            cwd=self._default_root_cwd(),
            context_version=1,
            last_command_text=None,
            last_command_at=None,
            pending_command_text=None,
            pending_plan_json={},
            pending_requested_at=None,
            closed_at=now,
            updated_at=now,
        )

    def _store_terminal_session(
        self,
        *,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        chat_jid: str,
        current: WhatsAppAgentTerminalSessionRecord,
        cli_mode_enabled: bool,
        cwd: str,
        context_version: int | None = None,
        last_command_text: str | None | object = _UNSET,
        last_command_at: datetime | None | object = _UNSET,
        pending_command_text: str | None | object = _UNSET,
        pending_plan_json: dict[str, Any] | object = _UNSET,
        pending_requested_at: datetime | None | object = _UNSET,
        closed_at: datetime | None | object = _UNSET,
    ) -> WhatsAppAgentTerminalSessionRecord:
        return self.store.upsert_whatsapp_agent_terminal_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=thread.contact_phone or session.contact_phone,
            chat_jid=chat_jid,
            cli_mode_enabled=cli_mode_enabled,
            cwd=cwd,
            context_version=context_version if context_version is not None else current.context_version,
            last_command_text=last_command_text,
            last_command_at=last_command_at,
            pending_command_text=pending_command_text,
            pending_plan_json=pending_plan_json,
            pending_requested_at=pending_requested_at,
            closed_at=closed_at,
            updated_at=datetime.now(UTC),
        )

    def _default_root_cwd(self) -> str:
        return str(Path(self.settings.normalized_whatsapp_cli_root))

    def _build_help_message(self, *, cli_mode_enabled: bool) -> str:
        cli_status = "ativa" if cli_mode_enabled else "fechada"
        return (
            "Comandos disponíveis para o Álvaro no WhatsApp CLI\n\n"
            f"Estado atual da CLI: `{cli_status}`\n\n"
            "`/`\n"
            "Mostra esta lista de comandos e o estado atual da CLI.\n\n"
            "`/agente`\n"
            "Abre a CLI do Cursar no WhatsApp.\n\n"
            "`/confirmar`\n"
            "Confirma a próxima ação sensível ou destrutiva pendente.\n\n"
            "`/cancelar`\n"
            "Descarta a execução pendente sem rodar nada no PC.\n\n"
            "`/clear`\n"
            "Limpa o contexto da CLI e reinicia a sessão no diretório raiz configurado.\n\n"
            "`/fechar`\n"
            "Encerra a CLI e volta a bloquear execução até novo `/agente`.\n\n"
            "Comandos diretos como `pwd`, `ls`, `cd`, `cat`, `rg`, `git status`, `pytest` e `npm run build` rodam como terminal.\n\n"
            "Pedidos em linguagem natural como \"analise esta pasta\", \"investigue esse erro\" ou \"corrija isso\" agora podem explorar o projeto automaticamente e devolver um relatório final.\n"
        )

    def _build_confirmation_message(
        self,
        *,
        command_text: str,
        plan: DeepSeekCliPlan,
        observations: list[CliExecutionObservation],
    ) -> str:
        action_lines: list[str] = []
        for index, action in enumerate(plan.actions[: max(1, self.settings.whatsapp_cli_max_steps)], start=1):
            if action.tool == "final":
                continue
            target = action.command.strip() or action.path.strip() or action.explanation.strip() or "(sem detalhe)"
            action_lines.append(f"{index}. `{action.tool}` {target}".strip())
        inspected_block = ""
        if observations:
            inspected_preview = []
            for item in observations[-3:]:
                inspected_preview.append(f"- `{item.command or item.tool}`")
            inspected_block = (
                "\nJa executei passos preparatorios nesta solicitacao:\n"
                f"{chr(10).join(inspected_preview)}\n"
            )
        summary = plan.summary.strip() or "Plano pronto para execução."
        return (
            "Confirmação necessária antes de executar no PC\n\n"
            f"Comando recebido: `{command_text}`\n"
            f"Resumo: {summary}\n"
            f"{inspected_block}\n"
            "Ações pendentes:\n"
            f"{chr(10).join(action_lines) if action_lines else '1. `exec` acao sensivel'}\n\n"
            "Envie `/confirmar` para executar agora ou `/cancelar` para descartar."
        )

    def _serialize_plan(self, plan: DeepSeekCliPlan) -> dict[str, Any]:
        return plan.model_dump(mode="json")

    def _deserialize_plan(self, payload: Any) -> DeepSeekCliPlan | None:
        if not isinstance(payload, dict) or not payload:
            return None
        try:
            return DeepSeekCliPlan.model_validate(payload)
        except Exception:
            return None

    def _has_pending_confirmation(self, terminal_session: WhatsAppAgentTerminalSessionRecord) -> bool:
        return bool(
            terminal_session.pending_command_text
            and terminal_session.pending_plan_json
            and terminal_session.pending_requested_at is not None
        )

    def _run_tool(self, *, action: DeepSeekCliAction, cwd: str) -> tuple[str, str]:
        if action.tool == "pwd":
            return cwd, cwd
        if action.tool == "cd":
            target = action.path or action.command
            if not target.strip():
                raise RuntimeError("Comando cd sem destino.")
            resolved = self._resolve_path(target, cwd=cwd)
            if not resolved.exists():
                raise RuntimeError(f"Diretório não encontrado: {resolved}")
            if not resolved.is_dir():
                raise RuntimeError(f"O caminho não é um diretório: {resolved}")
            return f"Diretório alterado para {resolved}", str(resolved)
        if action.tool == "write":
            return self._execute_write(action=action, cwd=cwd), cwd
        if action.tool == "ls":
            return self._run_process(["ls", *self._split_tool_args(action, tool_name="ls")], cwd=cwd), cwd
        if action.tool == "cat":
            return self._run_process(["cat", *self._split_tool_args(action, tool_name="cat")], cwd=cwd), cwd
        if action.tool == "find":
            return self._run_process(["find", *self._split_tool_args(action, tool_name="find")], cwd=cwd), cwd
        if action.tool == "head":
            return self._run_process(["head", *self._split_tool_args(action, tool_name="head")], cwd=cwd), cwd
        if action.tool == "tail":
            return self._run_process(["tail", *self._split_tool_args(action, tool_name="tail")], cwd=cwd), cwd
        if action.tool == "mkdir":
            return self._run_process(["mkdir", *self._split_tool_args(action, tool_name="mkdir")], cwd=cwd), cwd
        if action.tool == "touch":
            return self._run_process(["touch", *self._split_tool_args(action, tool_name="touch")], cwd=cwd), cwd
        if action.tool == "cp":
            return self._run_process(["cp", *self._split_tool_args(action, tool_name="cp")], cwd=cwd), cwd
        if action.tool == "mv":
            return self._run_process(["mv", *self._split_tool_args(action, tool_name="mv")], cwd=cwd), cwd
        if action.tool == "rm":
            return self._run_process(["rm", *self._split_tool_args(action, tool_name="rm")], cwd=cwd), cwd
        if action.tool == "rg":
            return self._run_process(["rg", *self._split_tool_args(action, tool_name="rg")], cwd=cwd), cwd
        if action.tool == "exec":
            command = action.command.strip() or action.path.strip()
            if not command:
                raise RuntimeError("Comando exec vazio.")
            return self._run_shell(command=command, cwd=cwd), cwd
        raise RuntimeError(f"Ferramenta da CLI não suportada: {action.tool}")

    def _execute_write(self, *, action: DeepSeekCliAction, cwd: str) -> str:
        target = action.path.strip() or action.command.strip()
        if not target:
            raise RuntimeError("Ferramenta write sem caminho de arquivo.")
        resolved = self._resolve_path(target, cwd=cwd)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if action.mode == "append" else "w"
        with resolved.open(mode, encoding="utf-8") as handle:
            handle.write(action.content)
        written_chars = len(action.content)
        return f"Arquivo atualizado: {resolved}\nModo: {action.mode}\nCaracteres gravados: {written_chars}"

    def _run_process(self, args: list[str], *, cwd: str) -> str:
        try:
            completed = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError(f"Comando não disponível no servidor: {args[0]}") from error
        output = (completed.stdout or "").strip()
        error_output = (completed.stderr or "").strip()
        if completed.returncode != 0:
            raise RuntimeError(error_output or output or f"Comando retornou código {completed.returncode}.")
        return output or "(sem saída)"

    def _run_shell(self, *, command: str, cwd: str) -> str:
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        output_parts = []
        if completed.stdout and completed.stdout.strip():
            output_parts.append(completed.stdout.strip())
        if completed.stderr and completed.stderr.strip():
            output_parts.append(completed.stderr.strip())
        combined = "\n".join(output_parts).strip()
        if completed.returncode != 0:
            raise RuntimeError(combined or f"Comando retornou código {completed.returncode}.")
        return combined or "(sem saída)"

    def _split_tool_args(self, action: DeepSeekCliAction, *, tool_name: str | None = None) -> list[str]:
        raw = action.command.strip() or action.path.strip()
        if not raw:
            return []
        parts = shlex.split(raw)
        normalized_tool = (tool_name or "").strip().lower()
        if normalized_tool and parts and parts[0].strip().lower() == normalized_tool:
            return parts[1:]
        return parts

    def _resolve_path(self, target: str, *, cwd: str) -> Path:
        candidate = Path(target.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        return candidate.resolve(strict=False)

    def _action_hits_sensitive_area(self, action: DeepSeekCliAction) -> bool:
        haystack = " ".join([action.tool, action.path, action.command, action.explanation]).casefold()
        return any(term in haystack for term in SENSITIVE_TERMS)

    def _format_output_chunks(self, *, tool_name: str, content: str) -> list[str]:
        normalized = content if content.strip() else "(sem saída)"
        chunk_size = max(300, self.settings.whatsapp_cli_output_chunk_chars)
        chunks = [normalized[index:index + chunk_size] for index in range(0, len(normalized), chunk_size)] or ["(sem saída)"]
        total = len(chunks)
        rendered: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            header = f"{tool_name} [{index}/{total}]\n" if total > 1 else f"{tool_name}\n"
            rendered.append(self._format_code_block(header + chunk))
        return rendered

    def _format_code_block(self, content: str) -> str:
        return f"```text\n{content.rstrip()}\n```"

    def _truncate(self, value: str, *, max_chars: int) -> str:
        normalized = str(value or "").strip()
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3] + "..."
