from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Awaitable, Callable
import logging
import shlex
import subprocess
import unicodedata

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

SAFE_DIRECT_TOOL_COMMANDS = {
    "pwd",
    "ls",
    "cd",
    "cat",
    "find",
    "head",
    "tail",
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

WHATSAPP_SUMMARY_CHUNK_CHARS = 900
WHATSAPP_TURN_DONE_MESSAGE = "Solicitação concluída. Agora estou aguardando sua próxima mensagem."
WHATSAPP_TURN_DONE_ERROR_MESSAGE = (
    "Essa solicitação foi encerrada com erro. Se quiser, mande a próxima mensagem com ajuste ou novo comando."
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


ProgressCallback = Callable[[CliOutboundMessage], Awaitable[None]]


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
        progress_callback: ProgressCallback | None = None,
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
                progress_callback=progress_callback,
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
                context_metadata=self._session_context_metadata(
                    contact_phone=thread.contact_phone,
                    current=terminal_session.context_metadata,
                    task_status="idle",
                    awaiting_user_turn=True,
                ),
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
                session_summary="",
                last_discovery_summary="",
                context_metadata=self._session_context_metadata(
                    contact_phone=thread.contact_phone,
                    task_status="idle",
                    awaiting_user_turn=True,
                ),
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
                session_summary="",
                last_discovery_summary="",
                context_metadata=self._session_context_metadata(
                    contact_phone=thread.contact_phone,
                    task_status="idle",
                    awaiting_user_turn=True,
                ),
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
                context_metadata=self._session_context_metadata(
                    contact_phone=thread.contact_phone,
                    current=terminal_session.context_metadata,
                    task_status="closed",
                    awaiting_user_turn=True,
                ),
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

        direct_command_plan = self._try_parse_direct_command(normalized_text)
        planned_heuristic = False
        direct_plan = direct_command_plan
        if direct_plan is None:
            direct_plan = self._try_build_heuristic_plan(
                message_text=normalized_text,
                cwd=terminal_session.cwd,
            )
            planned_heuristic = direct_plan is not None
        return_mode = "raw" if direct_command_plan is not None and not planned_heuristic else "summary"
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
            progress_callback=progress_callback,
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
        progress_callback: ProgressCallback | None,
    ) -> WhatsAppCliDispatchResult:
        current_cwd = terminal_session.cwd
        latest_model_run_id: str | None = None
        execution_error: str | None = None
        final_text_from_plan: str | None = None
        observations = list(prior_observations)
        executed_actions: list[DeepSeekCliAction] = []
        session_context = self._build_session_context(
            terminal_session=terminal_session,
            thread_id=thread.id,
            exclude_message_id=inbound_message.id,
        )
        plan = initial_plan
        max_rounds = max(1, min(4, self.settings.whatsapp_cli_max_steps))
        progress_started = False
        validation_progress_sent = False

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
                    context_metadata=self._session_context_metadata(
                        contact_phone=thread.contact_phone,
                        current=terminal_session.context_metadata,
                        active_task=command_text,
                        cwd=current_cwd,
                        observations=observations,
                        task_status="awaiting_confirmation",
                        awaiting_user_turn=True,
                    ),
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

                if progress_callback is not None and return_mode == "summary" and not progress_started:
                    progress_started = True
                    await progress_callback(
                        CliOutboundMessage(
                            text=(
                                f"Recebi sua solicitação e já comecei a analisar em `{current_cwd}`. "
                                "Vou te mandar o resultado quando terminar."
                            ),
                            generated_by="whatsapp_cli_progress",
                            metadata={"phase": "progress", "cwd": current_cwd},
                        )
                    )

                executed_any = True
                command_label = action.command.strip() or action.path.strip() or action.tool
                cwd_before = current_cwd
                try:
                    result_text, current_cwd = self._run_tool(action=action, cwd=current_cwd)
                    executed_actions.append(action)
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

        if (
            execution_error is None
            and return_mode == "summary"
            and self._should_run_post_edit_validation(executed_actions=executed_actions)
        ):
            if progress_callback is not None and not validation_progress_sent:
                validation_progress_sent = True
                await progress_callback(
                    CliOutboundMessage(
                        text="Fiz as alterações necessárias. Agora estou validando o resultado antes de te responder.",
                        generated_by="whatsapp_cli_progress",
                        metadata={"phase": "progress_validation", "cwd": current_cwd},
                    )
                )
            validation_observations, validation_error = self._run_post_edit_validation(
                cwd=current_cwd,
                executed_actions=executed_actions,
            )
            observations.extend(validation_observations)
            if validation_error is not None:
                execution_error = validation_error

        outbound_messages: list[CliOutboundMessage]
        session_summary: str
        discovery_summary = self._build_discovery_summary(observations=observations)
        if return_mode == "raw":
            outbound_messages = self._build_raw_output_messages(
                observations=observations,
                cwd=current_cwd,
                execution_error=execution_error,
            )
            session_summary = self._build_session_summary(
                command_text=command_text,
                final_text=observations[-1].output if observations else "",
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
            summary_text = self._normalize_summary_text(
                summary_text=summary_text,
                command_text=command_text,
                cwd=current_cwd,
                execution_error=execution_error,
            )
            outbound_messages = self._build_summary_output_messages(
                summary_text=summary_text,
                cwd=current_cwd,
                execution_error=execution_error,
                model_run_id=latest_model_run_id,
            )
            session_summary = self._build_session_summary(
                command_text=command_text,
                final_text=summary_text,
                execution_error=execution_error,
            )

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
            session_summary=session_summary,
            last_discovery_summary=discovery_summary,
            context_metadata=self._session_context_metadata(
                contact_phone=thread.contact_phone,
                current=terminal_session.context_metadata,
                active_task=command_text,
                cwd=current_cwd,
                observations=observations,
                task_status="failed" if execution_error is not None else "completed",
                awaiting_user_turn=True,
                last_error=execution_error,
            ),
            closed_at=None,
        )

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
        progress_callback: ProgressCallback | None,
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
                context_metadata=self._session_context_metadata(
                    contact_phone=thread.contact_phone,
                    current=terminal_session.context_metadata,
                    task_status="idle",
                    awaiting_user_turn=True,
                ),
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
            context_metadata=self._session_context_metadata(
                contact_phone=thread.contact_phone,
                current=terminal_session.context_metadata,
                active_task=pending.command_text,
                cwd=pending.cwd,
                observations=pending.observations,
                task_status="running",
                awaiting_user_turn=False,
            ),
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
            progress_callback=progress_callback,
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
                summary_text = (
                    "Não consegui sintetizar a resposta final automaticamente, "
                    f"mas a execução terminou com erro: {execution_error}"
                )
            else:
                summary_text = (
                    "Não consegui sintetizar a resposta final desta execução. "
                    "Se quiser, peça para eu repetir a análise ou rodar um comando mais específico."
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

    def _try_build_heuristic_plan(self, *, message_text: str, cwd: str) -> DeepSeekCliPlan | None:
        normalized = self._normalize_natural_text(message_text)
        if not self._looks_like_directory_analysis_request(normalized):
            return None
        target_path = self._infer_analysis_target_path(message_text=message_text, cwd=cwd)
        if target_path is None:
            return None
        actions = [
            DeepSeekCliAction(tool="pwd", explanation="Confirmar o diretório atual antes da análise."),
            DeepSeekCliAction(
                tool="cd",
                path=str(target_path),
                command=str(target_path),
                explanation="Entrar no diretório alvo da análise.",
            ),
            DeepSeekCliAction(
                tool="ls",
                command="ls -la",
                explanation="Listar o conteúdo imediato do diretório.",
            ),
            DeepSeekCliAction(
                tool="find",
                command="find . -maxdepth 2 -mindepth 1",
                explanation="Mapear a estrutura principal do diretório em até dois níveis.",
            ),
        ]
        return DeepSeekCliPlan(
            summary=f"Plano heurístico de análise do diretório {target_path}.",
            actions=actions,
        )

    def _matches_prefix(self, parts: list[str], prefix: tuple[str, ...]) -> bool:
        if len(parts) < len(prefix):
            return False
        return tuple(part.lower() for part in parts[: len(prefix)]) == prefix

    def _normalize_natural_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^a-z0-9/._ -]+", " ", ascii_only.casefold())
        return " ".join(cleaned.split())

    def _looks_like_directory_analysis_request(self, normalized_text: str) -> bool:
        analysis_terms = ("analise", "analisar", "analisa", "relatorio", "investigue", "inspecione", "veja")
        target_terms = ("pasta", "diretorio", "diretorio", "repo", "repositorio", "projeto", "downloads", "download")
        has_analysis_intent = any(term in normalized_text for term in analysis_terms)
        has_target = any(term in normalized_text for term in target_terms)
        continuation_patterns = ("e na pasta", "nessa pasta", "nesta pasta", "nessa pasta", "na pasta")
        return (has_analysis_intent and has_target) or any(pattern in normalized_text for pattern in continuation_patterns)

    def _infer_analysis_target_path(self, *, message_text: str, cwd: str) -> Path | None:
        normalized = self._normalize_natural_text(message_text)
        explicit_path = self._extract_explicit_path(message_text)
        if explicit_path is not None:
            return explicit_path
        if self._looks_like_downloads_request(normalized):
            downloads = self._find_downloads_directory()
            if downloads is not None:
                return downloads
        if any(token in normalized for token in {"repo", "repositorio", "projeto", "essa pasta", "esta pasta", "diretorio atual"}):
            return Path(cwd).resolve(strict=False)
        if "pasta" in normalized or "diretorio" in normalized:
            return Path(cwd).resolve(strict=False)
        return None

    def _extract_explicit_path(self, message_text: str) -> Path | None:
        raw = str(message_text or "")
        code_match = re.search(r"`([^`]+)`", raw)
        if code_match:
            return self._resolve_path(code_match.group(1), cwd=self.settings.normalized_whatsapp_cli_root)
        path_match = re.search(r"(/[^\s]+(?: [^\s]+)*)", raw)
        if path_match:
            return self._resolve_path(path_match.group(1), cwd=self.settings.normalized_whatsapp_cli_root)
        return None

    def _looks_like_downloads_request(self, normalized_text: str) -> bool:
        download_variants = (
            "download",
            "downloads",
            "dowload",
            "dowloads",
            "doeload",
            "doeloads",
            "donwload",
            "donwloads",
            "doweload",
            "doweloads",
            "downlod",
            "downlaod",
            "arquivos baixados",
        )
        return any(term in normalized_text for term in download_variants)

    def _find_downloads_directory(self) -> Path | None:
        candidates = [
            Path("/home/server/Downloads"),
            Path("/home/server/Download"),
            Path.home() / "Downloads",
            Path.home() / "Download",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve(strict=False)
        return None

    def _build_session_context(
        self,
        *,
        terminal_session: WhatsAppAgentTerminalSessionRecord,
        thread_id: str,
        exclude_message_id: str | None = None,
    ) -> str:
        sections: list[str] = []
        context_lines = self._render_session_context_metadata(terminal_session.context_metadata)
        if context_lines:
            sections.append("Contexto persistente da sessao:\n" + context_lines)
        if terminal_session.session_summary.strip():
            sections.append(
                "Resumo persistente da sessao:\n"
                f"{self._truncate(terminal_session.session_summary, max_chars=380)}"
            )
        if terminal_session.last_discovery_summary.strip():
            sections.append(
                "Ultimos achados observados:\n"
                f"{self._truncate(terminal_session.last_discovery_summary, max_chars=900)}"
            )
        recent_context = self._build_recent_cli_context(
            thread_id=thread_id,
            exclude_message_id=exclude_message_id,
        )
        if recent_context:
            sections.append("Historico recente da conversa CLI:\n" + recent_context)
        return "\n\n".join(section for section in sections if section.strip())

    def _build_recent_cli_context(self, *, thread_id: str, exclude_message_id: str | None = None) -> str:
        messages = self.store.list_whatsapp_agent_messages(thread_id=thread_id, limit=14)
        lines: list[str] = []
        for message in reversed(messages):
            if exclude_message_id and message.id == exclude_message_id:
                continue
            metadata = message.metadata if isinstance(message.metadata, dict) else {}
            generated_by = str(metadata.get("generated_by") or "").strip()
            phase = str(metadata.get("phase") or "").strip()
            interaction_mode = str(metadata.get("interaction_mode") or "").strip()
            if message.direction == "inbound":
                if interaction_mode != "cli" and not str(message.processing_status).startswith("cli_"):
                    continue
                role = "usuario"
            else:
                if not generated_by.startswith("whatsapp_cli"):
                    continue
                if phase in {"turn_complete_notice", "progress", "progress_validation"}:
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
            f"Execução encerrada com erro. Diretório atual: {cwd}"
            if execution_error is not None
            else f"Comando concluído. Diretório atual: {cwd}"
        )
        outbound.append(
            CliOutboundMessage(
                text=final_text,
                generated_by="whatsapp_cli_status",
                metadata={"phase": "finished", "cwd": cwd, "error": execution_error or ""},
            )
        )
        outbound.append(self._build_turn_done_message(cwd=cwd, execution_error=execution_error))
        return outbound

    def _build_summary_output_messages(
        self,
        *,
        summary_text: str,
        cwd: str,
        execution_error: str | None,
        model_run_id: str | None,
    ) -> list[CliOutboundMessage]:
        outbound: list[CliOutboundMessage] = []
        for chunk in self._split_whatsapp_text(summary_text):
            outbound.append(
                CliOutboundMessage(
                    text=chunk,
                    generated_by="whatsapp_cli_final",
                    metadata={
                        "phase": "final",
                        "cwd": cwd,
                        "model_run_id": model_run_id or "",
                        "execution_error": execution_error or "",
                    },
                )
            )
        outbound.append(self._build_turn_done_message(cwd=cwd, execution_error=execution_error))
        return outbound

    def _build_turn_done_message(self, *, cwd: str, execution_error: str | None) -> CliOutboundMessage:
        text = WHATSAPP_TURN_DONE_MESSAGE if execution_error is None else WHATSAPP_TURN_DONE_ERROR_MESSAGE
        return CliOutboundMessage(
            text=text,
            generated_by="whatsapp_cli_turn_done",
            metadata={
                "phase": "turn_complete_notice",
                "cwd": cwd,
                "execution_error": execution_error or "",
            },
        )

    def _normalize_summary_text(
        self,
        *,
        summary_text: str,
        command_text: str,
        cwd: str,
        execution_error: str | None,
    ) -> str:
        normalized = str(summary_text or "").strip()
        if normalized:
            return normalized
        if execution_error:
            return (
                f"Não consegui concluir `{command_text}` sem erro.\n\n"
                f"Erro observado: {execution_error}\n"
                f"Diretório atual: `{cwd}`"
            )
        return (
            f"Concluí a solicitação `{command_text}`.\n\n"
            f"Diretório atual: `{cwd}`"
        )

    def _build_session_summary(
        self,
        *,
        command_text: str,
        final_text: str,
        execution_error: str | None,
    ) -> str:
        if execution_error:
            base = f"Solicitação '{command_text}' encerrada com erro: {execution_error}"
        else:
            base = final_text.strip() or f"Solicitação '{command_text}' concluída."
        return self._truncate(" ".join(base.split()), max_chars=420)

    def _build_discovery_summary(self, *, observations: list[CliExecutionObservation]) -> str:
        if not observations:
            return ""
        lines: list[str] = []
        for item in observations[-4:]:
            status = "ok" if item.success else "erro"
            output_preview = self._truncate(" ".join(item.output.split()), max_chars=150)
            lines.append(f"- {status} | {item.command or item.tool}: {output_preview}")
        return "\n".join(lines)

    def _render_session_context_metadata(self, metadata: dict[str, Any]) -> str:
        if not isinstance(metadata, dict) or not metadata:
            return ""
        lines: list[str] = []
        if metadata.get("admin_actor"):
            lines.append("- ator_admin=true")
        if metadata.get("server_operator"):
            lines.append("- operando_servidor=true")
        channel = str(metadata.get("channel") or "").strip()
        if channel:
            lines.append(f"- canal={channel}")
        device_context = str(metadata.get("device_context") or "").strip()
        if device_context:
            lines.append(f"- dispositivo={device_context}")
        current_cwd = str(metadata.get("cwd") or "").strip()
        if current_cwd:
            lines.append(f"- cwd={self._truncate(current_cwd, max_chars=90)}")
        contact_phone = str(metadata.get("contact_phone") or "").strip()
        if contact_phone:
            lines.append(f"- contato={contact_phone}")
        active_task = str(metadata.get("active_task") or "").strip()
        if active_task:
            lines.append(f"- tarefa_atual={self._truncate(active_task, max_chars=140)}")
        task_status = str(metadata.get("task_status") or "").strip()
        if task_status:
            lines.append(f"- status_tarefa={task_status}")
        if metadata.get("awaiting_user_turn"):
            lines.append("- aguardando_usuario=true")
        recent_commands = metadata.get("recent_commands")
        if isinstance(recent_commands, list) and recent_commands:
            rendered_commands = ", ".join(
                self._truncate(str(item), max_chars=48) for item in recent_commands[:5] if str(item).strip()
            )
            if rendered_commands:
                lines.append(f"- comandos_recentes={rendered_commands}")
        inspected_paths = metadata.get("inspected_paths")
        if isinstance(inspected_paths, list) and inspected_paths:
            rendered_paths = ", ".join(
                self._truncate(str(item), max_chars=60) for item in inspected_paths[:5] if str(item).strip()
            )
            if rendered_paths:
                lines.append(f"- caminhos_inspecionados={rendered_paths}")
        last_validation_commands = metadata.get("last_validation_commands")
        if isinstance(last_validation_commands, list) and last_validation_commands:
            rendered_validations = ", ".join(
                self._truncate(str(item), max_chars=60)
                for item in last_validation_commands[:3]
                if str(item).strip()
            )
            if rendered_validations:
                lines.append(f"- validacoes={rendered_validations}")
        last_error = str(metadata.get("last_error") or "").strip()
        if last_error:
            lines.append(f"- ultimo_erro={self._truncate(last_error, max_chars=120)}")
        return "\n".join(lines)

    def _session_context_metadata(
        self,
        *,
        contact_phone: str | None,
        current: dict[str, Any] | None = None,
        active_task: str | None = None,
        cwd: str | None = None,
        observations: list[CliExecutionObservation] | None = None,
        task_status: str | None = None,
        awaiting_user_turn: bool | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        previous = current if isinstance(current, dict) else {}
        contact_is_admin = self.store.is_whatsapp_agent_admin_contact(
            user_id=self.settings.default_user_id,
            contact_phone=contact_phone,
        )
        owner_phone = self.settings.normalized_whatsapp_cli_owner_phone
        is_owner = bool(owner_phone and self.store.phone_matches(contact_phone, owner_phone))
        normalized_phone = self.store.normalize_contact_phone(contact_phone)
        metadata = {
            "admin_actor": bool(contact_is_admin or is_owner),
            "channel": "whatsapp_agent_cli",
            "contact_phone": normalized_phone,
            "device_context": "server_pc",
            "interaction_mode": "cli",
            "server_operator": True,
        }
        if active_task is not None:
            metadata["active_task"] = self._truncate(" ".join(active_task.split()), max_chars=220)
        elif previous.get("active_task"):
            metadata["active_task"] = previous.get("active_task")
        if task_status is not None:
            metadata["task_status"] = task_status
        elif previous.get("task_status"):
            metadata["task_status"] = previous.get("task_status")
        if awaiting_user_turn is not None:
            metadata["awaiting_user_turn"] = awaiting_user_turn
        elif "awaiting_user_turn" in previous:
            metadata["awaiting_user_turn"] = bool(previous.get("awaiting_user_turn"))
        if cwd:
            metadata["cwd"] = cwd
        elif previous.get("cwd"):
            metadata["cwd"] = previous.get("cwd")

        effective_observations = observations or []
        if effective_observations:
            metadata["recent_commands"] = self._collect_recent_commands(effective_observations)
            metadata["inspected_paths"] = self._collect_inspected_paths(effective_observations)
            metadata["last_validation_commands"] = self._collect_validation_commands(effective_observations)
        else:
            if isinstance(previous.get("recent_commands"), list):
                metadata["recent_commands"] = previous.get("recent_commands")
            if isinstance(previous.get("inspected_paths"), list):
                metadata["inspected_paths"] = previous.get("inspected_paths")
            if isinstance(previous.get("last_validation_commands"), list):
                metadata["last_validation_commands"] = previous.get("last_validation_commands")

        if last_error is None and task_status in {"completed", "idle", "closed"}:
            resolved_error = ""
        else:
            resolved_error = last_error if last_error is not None else str(previous.get("last_error") or "").strip()
        if resolved_error:
            metadata["last_error"] = self._truncate(resolved_error, max_chars=220)
        return metadata

    def _split_whatsapp_text(self, content: str) -> list[str]:
        normalized = str(content or "").strip()
        if not normalized:
            return ["Não encontrei conteúdo útil para responder."]
        chunk_limit = max(500, min(self.settings.whatsapp_cli_output_chunk_chars, WHATSAPP_SUMMARY_CHUNK_CHARS))
        if len(normalized) <= chunk_limit:
            return [normalized]

        parts: list[str] = []
        current = ""
        for block in [segment.strip() for segment in normalized.split("\n\n") if segment.strip()]:
            candidate = f"{current}\n\n{block}".strip() if current else block
            if len(candidate) <= chunk_limit:
                current = candidate
                continue
            if current:
                parts.append(current)
            while len(block) > chunk_limit:
                parts.append(block[:chunk_limit].rstrip())
                block = block[chunk_limit:].lstrip()
            current = block
        if current:
            parts.append(current)
        return parts or [normalized[:chunk_limit]]

    def _collect_recent_commands(self, observations: list[CliExecutionObservation]) -> list[str]:
        commands: list[str] = []
        for item in observations[-8:]:
            label = " ".join((item.command or item.tool).split()).strip()
            if not label or label in commands:
                continue
            commands.append(self._truncate(label, max_chars=80))
        return commands[-5:]

    def _collect_inspected_paths(self, observations: list[CliExecutionObservation]) -> list[str]:
        paths: list[str] = []
        for item in observations[-10:]:
            if item.tool not in {"cat", "edit", "write", "find", "head", "tail", "ls", "rg"}:
                continue
            candidate = self._extract_first_path_from_command(item.command)
            if not candidate:
                continue
            normalized = self._truncate(candidate, max_chars=100)
            if normalized not in paths:
                paths.append(normalized)
        return paths[-5:]

    def _collect_validation_commands(self, observations: list[CliExecutionObservation]) -> list[str]:
        validations: list[str] = []
        for item in observations[-8:]:
            if not self._looks_like_validation_command(item.command or item.tool):
                continue
            label = self._truncate(" ".join((item.command or item.tool).split()), max_chars=90)
            if label not in validations:
                validations.append(label)
        return validations[-3:]

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
        if action.tool in {"write", "edit", "mkdir", "touch", "cp", "mv"}:
            return self._mutating_path_outside_root(action=action, cwd=cwd)
        return False

    def _exec_requires_confirmation(self, command: str) -> bool:
        raw = command.strip()
        if not raw:
            return True
        unwrapped = self._unwrap_safe_shell_wrapper(raw)
        if unwrapped and unwrapped != raw:
            return self._exec_requires_confirmation(unwrapped)
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
        head = parts[0].strip().lower()
        if head in SAFE_DIRECT_TOOL_COMMANDS:
            return False
        for prefix in SAFE_EXEC_PREFIXES:
            if self._matches_prefix([part.lower() for part in parts], prefix):
                return False
        return True

    def _mutating_path_outside_root(self, *, action: DeepSeekCliAction, cwd: str) -> bool:
        targets: list[str] = []

        if action.tool in {"write", "edit", "mkdir", "touch"}:
            target = self._extract_primary_target(action=action, tool_name=action.tool)
            if target:
                targets.append(target)
        elif action.tool in {"cp", "mv"}:
            targets.extend(
                part
                for part in self._split_tool_args(action, tool_name=action.tool)
                if part and not part.startswith("-")
            )
        elif action.tool == "rm":
            targets.extend(
                part
                for part in self._split_tool_args(action, tool_name="rm")
                if part and not part.startswith("-")
            )

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
            session_summary="",
            last_discovery_summary="",
            context_metadata=self._session_context_metadata(
                contact_phone=thread.contact_phone,
                task_status="closed",
                awaiting_user_turn=True,
            ),
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
        session_summary: str | None | object = _UNSET,
        last_discovery_summary: str | None | object = _UNSET,
        context_metadata: dict[str, Any] | object = _UNSET,
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
            session_summary=session_summary,
            last_discovery_summary=last_discovery_summary,
            context_metadata=context_metadata,
            closed_at=closed_at,
            updated_at=datetime.now(UTC),
        )

    def _default_root_cwd(self) -> str:
        return str(Path(self.settings.normalized_whatsapp_cli_root))

    def _build_help_message(self, *, cli_mode_enabled: bool) -> str:
        cli_status = "ativa" if cli_mode_enabled else "fechada"
        return (
            "WhatsApp CLI do AuraCore\n\n"
            f"Estado atual: `{cli_status}`\n\n"
            "`/agente` abre a CLI.\n"
            "`/fechar` encerra a CLI.\n"
            "`/clear` limpa o contexto da sessão.\n"
            "`/confirmar` executa uma ação sensível pendente.\n"
            "`/cancelar` descarta a ação pendente.\n\n"
            "Comandos diretos como `pwd`, `ls`, `cd`, `cat`, `rg`, `git status`, `pytest` e `npm run build` rodam como terminal.\n"
            "O modo agente tambem pode editar arquivos com mais precisao e validar automaticamente depois da alteracao.\n\n"
            "Pedidos naturais como \"analise esta pasta\", \"veja esse erro\" ou \"corrija isso\" usam modo agente: investigam, executam e depois respondem com relatório final.\n"
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
            "Confirmação necessária para continuar\n\n"
            f"Pedido: `{command_text}`\n"
            f"Resumo: {summary}\n"
            f"{inspected_block}\n"
            "Próximas ações:\n"
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
            target = self._extract_primary_target(action=action, tool_name="cd")
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
        if action.tool == "edit":
            return self._execute_edit(action=action, cwd=cwd), cwd
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
        target = self._extract_primary_target(action=action, tool_name="write")
        if not target:
            raise RuntimeError("Ferramenta write sem caminho de arquivo.")
        resolved = self._resolve_path(target, cwd=cwd)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if action.mode == "append" else "w"
        with resolved.open(mode, encoding="utf-8") as handle:
            handle.write(action.content)
        written_chars = len(action.content)
        return f"Arquivo atualizado: {resolved}\nModo: {action.mode}\nCaracteres gravados: {written_chars}"

    def _execute_edit(self, *, action: DeepSeekCliAction, cwd: str) -> str:
        target = self._extract_primary_target(action=action, tool_name="edit")
        if not target:
            raise RuntimeError("Ferramenta edit sem caminho de arquivo.")
        if not action.old_text:
            raise RuntimeError("Ferramenta edit sem old_text para localizar o trecho atual.")
        resolved = self._resolve_path(target, cwd=cwd)
        if not resolved.exists():
            raise RuntimeError(f"Arquivo para editar não encontrado: {resolved}")
        original = resolved.read_text(encoding="utf-8")
        occurrences = original.count(action.old_text)
        if occurrences == 0:
            raise RuntimeError(f"O trecho old_text não foi encontrado em {resolved}.")
        if occurrences > 1:
            raise RuntimeError(f"O trecho old_text apareceu mais de uma vez em {resolved}; preciso de um alvo mais específico.")
        updated = original.replace(action.old_text, action.new_text, 1)
        resolved.write_text(updated, encoding="utf-8")
        return (
            f"Arquivo editado: {resolved}\n"
            "Modo: substituicao estruturada\n"
            f"Trecho antigo: {len(action.old_text)} caracteres\n"
            f"Trecho novo: {len(action.new_text)} caracteres"
        )

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

    def _extract_primary_target(self, *, action: DeepSeekCliAction, tool_name: str | None = None) -> str:
        args = self._split_tool_args(action, tool_name=tool_name)
        for part in args:
            if part and not part.startswith("-"):
                return part
        raw_path = action.path.strip()
        if raw_path:
            return raw_path
        raw_command = action.command.strip()
        if not raw_command:
            return ""
        try:
            parts = shlex.split(raw_command)
        except ValueError:
            return raw_command
        if tool_name and parts and parts[0].strip().lower() == tool_name.strip().lower():
            parts = parts[1:]
        cleaned = [part for part in parts if part and not part.startswith("-")]
        if cleaned:
            return cleaned[0]
        return raw_command

    def _unwrap_safe_shell_wrapper(self, command: str) -> str:
        raw = command.strip()
        if not raw:
            return raw
        try:
            parts = shlex.split(raw)
        except ValueError:
            return raw
        if len(parts) < 3:
            return raw
        shell_name = Path(parts[0]).name.lower()
        if shell_name not in {"bash", "sh", "zsh"}:
            return raw
        if parts[1] not in {"-lc", "-c"}:
            return raw
        inner_command = parts[2].strip()
        return inner_command or raw

    def _resolve_path(self, target: str, *, cwd: str) -> Path:
        candidate = Path(target.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        return candidate.resolve(strict=False)

    def _should_run_post_edit_validation(self, *, executed_actions: list[DeepSeekCliAction]) -> bool:
        has_mutation = any(action.tool in {"write", "edit", "mkdir", "touch", "cp", "mv", "rm"} for action in executed_actions)
        if not has_mutation:
            return False
        return not any(
            action.tool == "exec" and self._looks_like_validation_command(action.command)
            for action in executed_actions
        )

    def _run_post_edit_validation(
        self,
        *,
        cwd: str,
        executed_actions: list[DeepSeekCliAction],
    ) -> tuple[list[CliExecutionObservation], str | None]:
        validation_commands = self._infer_validation_commands(cwd=cwd, executed_actions=executed_actions)
        observations: list[CliExecutionObservation] = []
        for command in validation_commands:
            try:
                output = self._run_shell(command=command, cwd=cwd)
                observations.append(
                    CliExecutionObservation(
                        tool="exec",
                        command=command,
                        cwd_before=cwd,
                        cwd_after=cwd,
                        explanation="Validacao automatica apos alteracoes.",
                        output=output,
                        success=True,
                    )
                )
            except Exception as error:
                error_text = str(error)
                observations.append(
                    CliExecutionObservation(
                        tool="exec",
                        command=command,
                        cwd_before=cwd,
                        cwd_after=cwd,
                        explanation="Validacao automatica apos alteracoes.",
                        output=error_text,
                        success=False,
                    )
                )
                return observations, f"Validação automática falhou em `{command}`: {error_text}"
        return observations, None

    def _infer_validation_commands(
        self,
        *,
        cwd: str,
        executed_actions: list[DeepSeekCliAction],
    ) -> list[str]:
        mutated_paths = self._collect_mutated_paths(cwd=cwd, executed_actions=executed_actions)
        if not mutated_paths:
            return []
        python_paths = [path for path in mutated_paths if path.suffix == ".py" and path.exists()]
        if python_paths:
            quoted = " ".join(shlex.quote(str(path)) for path in python_paths[:12])
            return [f"python3 -m py_compile {quoted}"]
        package_json = self._find_package_json(start_cwd=cwd)
        if package_json is not None and any(path.suffix in {".js", ".jsx", ".ts", ".tsx", ".css", ".scss"} for path in mutated_paths):
            return self._infer_node_validation_commands(package_json)
        return []

    def _collect_mutated_paths(self, *, cwd: str, executed_actions: list[DeepSeekCliAction]) -> list[Path]:
        mutated: list[Path] = []
        for action in executed_actions:
            if action.tool not in {"write", "edit", "mkdir", "touch", "cp", "mv", "rm"}:
                continue
            for target in self._extract_action_targets(action=action, cwd=cwd):
                if target not in mutated:
                    mutated.append(target)
        return mutated

    def _extract_action_targets(self, *, action: DeepSeekCliAction, cwd: str) -> list[Path]:
        if action.tool in {"write", "edit", "mkdir", "touch"}:
            target = self._extract_primary_target(action=action, tool_name=action.tool)
            if target:
                return [self._resolve_path(target, cwd=cwd)]
            return []
        if action.tool in {"cp", "mv"}:
            cleaned = [part for part in self._split_tool_args(action, tool_name=action.tool) if part and not part.startswith("-")]
            return [self._resolve_path(part, cwd=cwd) for part in cleaned[-2:]]
        if action.tool == "rm":
            cleaned = [part for part in self._split_tool_args(action, tool_name="rm") if part and not part.startswith("-")]
            return [self._resolve_path(part, cwd=cwd) for part in cleaned]
        return []

    def _find_package_json(self, *, start_cwd: str) -> Path | None:
        current = Path(start_cwd).resolve(strict=False)
        root = Path(self.settings.normalized_whatsapp_cli_root).resolve(strict=False)
        for candidate_dir in [current, *current.parents]:
            package_json = candidate_dir / "package.json"
            if package_json.exists():
                return package_json
            if candidate_dir == root:
                break
        return None

    def _infer_node_validation_commands(self, package_json_path: Path) -> list[str]:
        try:
            package_data = json.loads(package_json_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        scripts = package_data.get("scripts")
        if not isinstance(scripts, dict):
            return []
        package_manager = "npm"
        if (package_json_path.parent / "pnpm-lock.yaml").exists():
            package_manager = "pnpm"
        elif (package_json_path.parent / "yarn.lock").exists():
            package_manager = "yarn"
        if "build" in scripts:
            return [self._package_manager_command(package_manager, "build")]
        if "lint" in scripts:
            return [self._package_manager_command(package_manager, "lint")]
        if "test" in scripts:
            return [self._package_manager_command(package_manager, "test")]
        return []

    def _package_manager_command(self, package_manager: str, script_name: str) -> str:
        if package_manager == "npm":
            return f"npm run {script_name}"
        return f"{package_manager} {script_name}"

    def _looks_like_validation_command(self, command: str) -> bool:
        normalized = " ".join(str(command or "").split()).strip().lower()
        if not normalized:
            return False
        markers = ("pytest", "test", "build", "lint", "py_compile", "mypy", "ruff", "tsc", "cargo test", "go test")
        return any(marker in normalized for marker in markers)

    def _extract_first_path_from_command(self, command: str) -> str | None:
        normalized = str(command or "").strip()
        if not normalized:
            return None
        try:
            parts = shlex.split(normalized)
        except ValueError:
            return None
        for part in parts[1:]:
            if part.startswith("-"):
                continue
            if "/" in part or "." in Path(part).name:
                return part
        return None

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
