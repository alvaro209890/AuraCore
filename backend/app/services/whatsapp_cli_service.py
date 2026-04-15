from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from pathlib import Path
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
    "systemctl",
    "service",
    "tunnel",
    "tunel",
}


@dataclass(slots=True)
class CliOutboundMessage:
    text: str
    generated_by: str
    metadata: dict[str, object]


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
            return self._confirm_pending_execution(
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
                            "Envie comandos normalmente. Use `/confirmar`, `/cancelar`, `/clear` e `/fechar` para controlar a sessão."
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

        return await self._prepare_cli_execution(
            message_text=normalized_text,
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            terminal_session=terminal_session,
        )

    async def _prepare_cli_execution(
        self,
        *,
        message_text: str,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        chat_jid: str,
        terminal_session: WhatsAppAgentTerminalSessionRecord,
    ) -> WhatsAppCliDispatchResult:
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        cwd = terminal_session.cwd
        plan: DeepSeekCliPlan | None = None
        plan_error: str | None = None
        model_run_id: str | None = None

        try:
            plan = await self.deepseek_service.extract_cli_plan(
                user_message=message_text,
                cwd=cwd,
                cli_mode_enabled=True,
            )
        except Exception as error:
            plan_error = str(error)
            logger.warning("whatsapp_cli_plan_failed thread_id=%s detail=%s", thread.id, plan_error)

        plan_elapsed_ms = int((perf_counter() - started_clock) * 1000)
        model_run = self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=None,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="whatsapp_cli_plan",
            success=plan_error is None,
            latency_ms=plan_elapsed_ms,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=plan_error,
            created_at=started_at,
        )
        model_run_id = model_run.id if model_run is not None else None

        if plan is None:
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=True,
                cwd=cwd,
                last_command_text=message_text,
                last_command_at=datetime.now(UTC),
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
                closed_at=None,
            )
            return WhatsAppCliDispatchResult(
                action="cli_failed_deepseek",
                outbound_messages=[
                    CliOutboundMessage(
                        text=self._format_code_block(
                            "ERRO\nDeepSeek indisponível para planejar a execução da CLI. Nenhum comando foi executado."
                        ),
                        generated_by="whatsapp_cli_error",
                        metadata={"phase": "deepseek_unavailable", "cwd": cwd},
                    )
                ],
                terminal_session=terminal_session,
                model_run_id=model_run_id,
            )

        actions = plan.actions[: max(1, self.settings.whatsapp_cli_max_steps)]
        if not actions:
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=True,
                cwd=cwd,
                last_command_text=message_text,
                last_command_at=datetime.now(UTC),
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
                closed_at=None,
            )
            return WhatsAppCliDispatchResult(
                action="cli_failed_empty_plan",
                outbound_messages=[
                    CliOutboundMessage(
                        text=self._format_code_block(
                            "ERRO\nDeepSeek não retornou nenhuma ação executável para esta mensagem. Nenhum comando foi executado."
                        ),
                        generated_by="whatsapp_cli_error",
                        metadata={"phase": "empty_plan", "cwd": cwd},
                    )
                ],
                terminal_session=terminal_session,
                model_run_id=model_run_id,
            )

        executable_actions = [action for action in actions if action.tool != "final"]
        if not executable_actions:
            terminal_session = self._store_terminal_session(
                thread=thread,
                session=session,
                chat_jid=chat_jid,
                current=terminal_session,
                cli_mode_enabled=True,
                cwd=cwd,
                last_command_text=message_text,
                last_command_at=datetime.now(UTC),
                pending_command_text=None,
                pending_plan_json={},
                pending_requested_at=None,
                closed_at=None,
            )
            messages = [
                CliOutboundMessage(
                    text=action.explanation.strip(),
                    generated_by="whatsapp_cli_plan",
                    metadata={"tool": "final"},
                )
                for action in actions
                if action.tool == "final" and action.explanation.strip()
            ]
            return WhatsAppCliDispatchResult(
                action="cli_final_only",
                outbound_messages=messages or [
                    CliOutboundMessage(
                        text="Nenhuma ação de sistema foi necessária para esta mensagem.",
                        generated_by="whatsapp_cli_plan",
                        metadata={"tool": "final"},
                    )
                ],
                terminal_session=terminal_session,
                model_run_id=model_run_id,
            )

        restricted_allowed = bool(
            plan.explicit_sensitive_request or self._message_has_explicit_sensitive_request(message_text)
        )
        terminal_session = self._store_terminal_session(
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            current=terminal_session,
            cli_mode_enabled=True,
            cwd=cwd,
            pending_command_text=message_text,
            pending_plan_json=self._serialize_plan(plan),
            pending_requested_at=datetime.now(UTC),
            closed_at=None,
        )
        return WhatsAppCliDispatchResult(
            action="cli_confirmation_requested",
            outbound_messages=[
                CliOutboundMessage(
                    text=self._build_confirmation_message(
                        command_text=message_text,
                        plan=plan,
                        restricted_allowed=restricted_allowed,
                    ),
                    generated_by="whatsapp_cli_control",
                    metadata={
                        "phase": "awaiting_confirmation",
                        "cwd": cwd,
                        "plan_summary": plan.summary,
                        "model_run_id": model_run_id or "",
                        "source_inbound_message_id": inbound_message.whatsapp_message_id or "",
                    },
                )
            ],
            terminal_session=terminal_session,
            model_run_id=model_run_id,
        )

    def _confirm_pending_execution(
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

        plan = self._deserialize_plan(terminal_session.pending_plan_json)
        if plan is None:
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

        return self._execute_confirmed_plan(
            command_text=terminal_session.pending_command_text or terminal_session.last_command_text or "",
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            terminal_session=terminal_session,
            plan=plan,
        )

    def _execute_confirmed_plan(
        self,
        *,
        command_text: str,
        inbound_message: WhatsAppAgentMessageRecord,
        thread: WhatsAppAgentThreadRecord,
        session: WhatsAppAgentThreadSessionRecord,
        chat_jid: str,
        terminal_session: WhatsAppAgentTerminalSessionRecord,
        plan: DeepSeekCliPlan,
    ) -> WhatsAppCliDispatchResult:
        cwd = terminal_session.cwd
        outbound_messages: list[CliOutboundMessage] = [
            CliOutboundMessage(
                text=f"⚙️ Executando comando confirmado: `{command_text}`...",
                generated_by="whatsapp_cli_status",
                metadata={"phase": "started", "cwd": cwd},
            )
        ]
        restricted_allowed = bool(
            plan.explicit_sensitive_request or self._message_has_explicit_sensitive_request(command_text)
        )
        execution_error: str | None = None
        executed_tools: list[str] = []

        try:
            for action in plan.actions[: max(1, self.settings.whatsapp_cli_max_steps)]:
                if action.tool == "final":
                    if action.explanation.strip():
                        outbound_messages.append(
                            CliOutboundMessage(
                                text=action.explanation.strip(),
                                generated_by="whatsapp_cli_plan",
                                metadata={"tool": "final"},
                            )
                        )
                    continue

                if not restricted_allowed and self._action_hits_sensitive_area(action):
                    raise PermissionError(
                        "Comando bloqueado para proteger GeoServer, Cloudflare Tunnel e serviços do sistema. "
                        "Peça isso explicitamente na mensagem para liberar."
                    )

                result_text, cwd = self._run_tool(action=action, cwd=cwd)
                executed_tools.append(action.tool)
                for chunk in self._format_output_chunks(tool_name=action.tool, content=result_text):
                    outbound_messages.append(
                        CliOutboundMessage(
                            text=chunk,
                            generated_by="whatsapp_cli_tool",
                            metadata={
                                "tool": action.tool,
                                "cwd": cwd,
                                "command": action.command or action.path,
                                "explanation": action.explanation,
                            },
                        )
                    )
        except Exception as error:
            execution_error = str(error)
            outbound_messages.append(
                CliOutboundMessage(
                    text=self._format_code_block(f"ERRO\n{execution_error}"),
                    generated_by="whatsapp_cli_error",
                    metadata={"phase": "error", "cwd": cwd},
                )
            )

        finished_at = datetime.now(UTC)
        terminal_session = self._store_terminal_session(
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            current=terminal_session,
            cli_mode_enabled=True,
            cwd=cwd,
            last_command_text=command_text,
            last_command_at=finished_at,
            pending_command_text=None,
            pending_plan_json={},
            pending_requested_at=None,
            closed_at=None,
        )
        final_text = (
            f"✅ Comando finalizado. Diretório atual: {cwd}"
            if execution_error is None
            else f"⚠️ Execução encerrada com erro. Diretório atual: {cwd}"
        )
        outbound_messages.append(
            CliOutboundMessage(
                text=final_text,
                generated_by="whatsapp_cli_status",
                metadata={
                    "phase": "finished",
                    "cwd": cwd,
                    "executed_tools": executed_tools,
                    "plan_summary": plan.summary,
                    "error": execution_error or "",
                    "source_inbound_message_id": inbound_message.whatsapp_message_id or "",
                },
            )
        )
        return WhatsAppCliDispatchResult(
            action="cli_executed" if execution_error is None else "cli_failed",
            outbound_messages=outbound_messages,
            terminal_session=terminal_session,
        )

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
            "Abre a CLI do Cursar no WhatsApp e passa a tratar as próximas mensagens como comandos.\n\n"
            "`/confirmar`\n"
            "Confirma e executa o último plano pendente preparado pelo DeepSeek.\n\n"
            "`/cancelar`\n"
            "Descarta a execução pendente sem rodar nada no PC.\n\n"
            "`/clear`\n"
            "Limpa o contexto da CLI e reinicia a sessão no diretório raiz configurado.\n\n"
            "`/fechar`\n"
            "Encerra a CLI e volta a bloquear execução até novo `/agente`.\n\n"
            "`pwd`\n"
            "Mostra o diretório atual da sessão.\n\n"
            "`ls` ou `ls -la`\n"
            "Lista arquivos e diretórios no caminho atual ou no caminho informado.\n\n"
            "`cd <caminho>`\n"
            "Muda o diretório persistente da sessão.\n\n"
            "`cat <arquivo>`\n"
            "Lê o conteúdo de um arquivo.\n\n"
            "`write <arquivo>`\n"
            "Escreve ou atualiza arquivo quando o pedido trouxer o conteúdo explicitamente.\n\n"
            "`find`, `head`, `tail`\n"
            "Localiza arquivos ou mostra começo e fim de arquivos maiores.\n\n"
            "`mkdir`, `touch`, `cp`, `mv`, `rm`\n"
            "Cria, copia, move e remove arquivos ou diretórios quando o pedido for explícito.\n\n"
            "`exec` ou comandos livres\n"
            "Executa comandos de sistema no diretório atual, sempre planejados pelo DeepSeek e sempre com confirmação antes da execução.\n"
        )

    def _build_confirmation_message(
        self,
        *,
        command_text: str,
        plan: DeepSeekCliPlan,
        restricted_allowed: bool,
    ) -> str:
        action_lines: list[str] = []
        for index, action in enumerate(plan.actions[: max(1, self.settings.whatsapp_cli_max_steps)], start=1):
            target = action.command.strip() or action.path.strip() or action.explanation.strip() or "(sem detalhe)"
            action_lines.append(f"{index}. `{action.tool}` {target}".strip())
        summary = plan.summary.strip() or "Plano pronto para execução."
        sensitive_note = (
            "\nPedido sensível explícito detectado: a execução inclui ação sobre serviço ou processo."
            if restricted_allowed
            else ""
        )
        return (
            "Confirmação necessária antes de executar no PC\n\n"
            f"Comando recebido: `{command_text}`\n"
            f"Resumo: {summary}\n\n"
            "Ações planejadas:\n"
            f"{chr(10).join(action_lines)}"
            f"{sensitive_note}\n\n"
            "Envie `/confirmar` para executar agora ou `/cancelar` para descartar."
        )

    def _serialize_plan(self, plan: DeepSeekCliPlan) -> dict[str, Any]:
        return plan.model_dump(mode="json")

    def _deserialize_plan(self, payload: dict[str, Any]) -> DeepSeekCliPlan | None:
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
            return self._run_process(["ls", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "cat":
            return self._run_process(["cat", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "find":
            return self._run_process(["find", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "head":
            return self._run_process(["head", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "tail":
            return self._run_process(["tail", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "mkdir":
            return self._run_process(["mkdir", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "touch":
            return self._run_process(["touch", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "cp":
            return self._run_process(["cp", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "mv":
            return self._run_process(["mv", *self._split_tool_args(action)], cwd=cwd), cwd
        if action.tool == "rm":
            return self._run_process(["rm", *self._split_tool_args(action)], cwd=cwd), cwd
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
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
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
            timeout=45,
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

    def _split_tool_args(self, action: DeepSeekCliAction) -> list[str]:
        raw = action.command.strip() or action.path.strip()
        if not raw:
            return []
        return shlex.split(raw)

    def _resolve_path(self, target: str, *, cwd: str) -> Path:
        candidate = Path(target.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        return candidate.resolve(strict=False)

    def _message_has_explicit_sensitive_request(self, message_text: str) -> bool:
        lowered = message_text.casefold()
        if not any(term in lowered for term in SENSITIVE_TERMS):
            return False
        return any(
            marker in lowered
            for marker in {
                "pode",
                "reinicie",
                "restart",
                "pare",
                "suba",
                "rode",
                "execute",
                "mexa",
                "altere",
                "mexer",
            }
        )

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
