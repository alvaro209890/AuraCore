from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
from time import perf_counter
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

SENSITIVE_TERMS = {
    "cloudflared",
    "cloudflare",
    "docker",
    "geoserver",
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

        if control_command == "/agente":
            root_cwd = self._default_root_cwd()
            terminal_session = self.store.upsert_whatsapp_agent_terminal_session(
                user_id=self.settings.default_user_id,
                thread_id=thread.id,
                contact_phone=thread.contact_phone,
                chat_jid=chat_jid,
                cli_mode_enabled=True,
                cwd=root_cwd,
                context_version=max(1, terminal_session.context_version),
                last_command_text=None,
                last_command_at=None,
                closed_at=None,
                updated_at=datetime.now(UTC),
            )
            return WhatsAppCliDispatchResult(
                action="cli_opened",
                outbound_messages=[
                    CliOutboundMessage(
                        text=(
                            "CLI ativada.\n\n"
                            f"Diretorio inicial: `{terminal_session.cwd}`\n"
                            "Envie comandos normalmente. Use `/clear` para resetar o contexto e `/fechar` para encerrar."
                        ),
                        generated_by="whatsapp_cli_control",
                        metadata={"control_command": "/agente", "cwd": terminal_session.cwd},
                    )
                ],
                terminal_session=terminal_session,
            )

        if control_command == "/clear":
            root_cwd = self._default_root_cwd()
            terminal_session = self.store.upsert_whatsapp_agent_terminal_session(
                user_id=self.settings.default_user_id,
                thread_id=thread.id,
                contact_phone=thread.contact_phone,
                chat_jid=chat_jid,
                cli_mode_enabled=True,
                cwd=root_cwd,
                context_version=max(1, terminal_session.context_version + 1),
                last_command_text=None,
                last_command_at=None,
                closed_at=None,
                updated_at=datetime.now(UTC),
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
            terminal_session = self.store.upsert_whatsapp_agent_terminal_session(
                user_id=self.settings.default_user_id,
                thread_id=thread.id,
                contact_phone=thread.contact_phone,
                chat_jid=chat_jid,
                cli_mode_enabled=False,
                cwd=terminal_session.cwd,
                context_version=terminal_session.context_version,
                last_command_text=terminal_session.last_command_text,
                last_command_at=terminal_session.last_command_at,
                closed_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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

        return await self._execute_cli_message(
            message_text=normalized_text,
            inbound_message=inbound_message,
            thread=thread,
            session=session,
            chat_jid=chat_jid,
            terminal_session=terminal_session,
        )

    async def _execute_cli_message(
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
        status_text = f"⚙️ Processando comando: `{message_text}`..."
        outbound_messages: list[CliOutboundMessage] = [
            CliOutboundMessage(
                text=status_text,
                generated_by="whatsapp_cli_status",
                metadata={"phase": "started", "cwd": cwd},
            )
        ]
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
            outbound_messages.append(
                CliOutboundMessage(
                    text=self._format_code_block(
                        "ERRO\nDeepSeek indisponível para planejar a execução da CLI. Nenhum comando foi executado."
                    ),
                    generated_by="whatsapp_cli_error",
                    metadata={"phase": "deepseek_unavailable", "cwd": cwd},
                )
            )
            finished_at = datetime.now(UTC)
            terminal_session = self.store.upsert_whatsapp_agent_terminal_session(
                user_id=self.settings.default_user_id,
                thread_id=thread.id,
                contact_phone=thread.contact_phone or session.contact_phone,
                chat_jid=chat_jid,
                cli_mode_enabled=True,
                cwd=cwd,
                context_version=terminal_session.context_version,
                last_command_text=message_text,
                last_command_at=finished_at,
                closed_at=None,
                updated_at=finished_at,
            )
            outbound_messages.append(
                CliOutboundMessage(
                    text=f"⚠️ Execução encerrada sem DeepSeek. Diretório atual: {cwd}",
                    generated_by="whatsapp_cli_status",
                    metadata={"phase": "finished", "cwd": cwd, "model_run_id": model_run_id, "error": plan_error},
                )
            )
            return WhatsAppCliDispatchResult(
                action="cli_failed_deepseek",
                outbound_messages=outbound_messages,
                terminal_session=terminal_session,
                model_run_id=model_run_id,
            )

        restricted_allowed = bool(
            (plan and plan.explicit_sensitive_request) or self._message_has_explicit_sensitive_request(message_text)
        )
        actions = plan.actions[: max(1, self.settings.whatsapp_cli_max_steps)]

        if not actions:
            outbound_messages.append(
                CliOutboundMessage(
                    text=self._format_code_block(
                        "ERRO\nDeepSeek não retornou nenhuma ação executável para esta mensagem. Nenhum comando foi executado."
                    ),
                    generated_by="whatsapp_cli_error",
                    metadata={"phase": "empty_plan", "cwd": cwd},
                )
            )
            finished_at = datetime.now(UTC)
            terminal_session = self.store.upsert_whatsapp_agent_terminal_session(
                user_id=self.settings.default_user_id,
                thread_id=thread.id,
                contact_phone=thread.contact_phone or session.contact_phone,
                chat_jid=chat_jid,
                cli_mode_enabled=True,
                cwd=cwd,
                context_version=terminal_session.context_version,
                last_command_text=message_text,
                last_command_at=finished_at,
                closed_at=None,
                updated_at=finished_at,
            )
            outbound_messages.append(
                CliOutboundMessage(
                    text=f"⚠️ Execução encerrada sem plano válido. Diretório atual: {cwd}",
                    generated_by="whatsapp_cli_status",
                    metadata={"phase": "finished", "cwd": cwd, "model_run_id": model_run_id},
                )
            )
            return WhatsAppCliDispatchResult(
                action="cli_failed_empty_plan",
                outbound_messages=outbound_messages,
                terminal_session=terminal_session,
                model_run_id=model_run_id,
            )

        execution_error: str | None = None
        executed_tools: list[str] = []
        try:
            for action in actions:
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
                        "Comando bloqueado para proteger GeoServer, Cloudflare Tunnel e servicos do sistema. "
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
        terminal_session = self.store.upsert_whatsapp_agent_terminal_session(
            user_id=self.settings.default_user_id,
            thread_id=thread.id,
            contact_phone=thread.contact_phone or session.contact_phone,
            chat_jid=chat_jid,
            cli_mode_enabled=True,
            cwd=cwd,
            context_version=terminal_session.context_version,
            last_command_text=message_text,
            last_command_at=finished_at,
            closed_at=None,
            updated_at=finished_at,
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
                    "plan_summary": plan.summary if plan is not None else "",
                    "model_run_id": model_run_id,
                    "error": execution_error,
                    "source_inbound_message_id": inbound_message.whatsapp_message_id,
                },
            )
        )
        return WhatsAppCliDispatchResult(
            action="cli_executed" if execution_error is None else "cli_failed",
            outbound_messages=outbound_messages,
            terminal_session=terminal_session,
            model_run_id=model_run_id,
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
            closed_at=now,
            updated_at=now,
        )

    def _default_root_cwd(self) -> str:
        return str(Path(self.settings.normalized_whatsapp_cli_root))

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
        haystack = " ".join(
            [
                action.tool,
                action.path,
                action.command,
                action.explanation,
            ]
        ).casefold()
        return any(term in haystack for term in SENSITIVE_TERMS)

    def _format_output_chunks(self, *, tool_name: str, content: str) -> list[str]:
        normalized = content if content.strip() else "(sem saída)"
        chunk_size = max(300, self.settings.whatsapp_cli_output_chunk_chars)
        chunks = [
            normalized[index:index + chunk_size]
            for index in range(0, len(normalized), chunk_size)
        ] or ["(sem saída)"]
        total = len(chunks)
        rendered: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            header = f"{tool_name} [{index}/{total}]\n" if total > 1 else f"{tool_name}\n"
            rendered.append(self._format_code_block(header + chunk))
        return rendered

    def _format_code_block(self, content: str) -> str:
        return f"```text\n{content.rstrip()}\n```"
