from __future__ import annotations

from dataclasses import dataclass
import threading

from app.config import Settings
from app.services.agenda_guardian_service import AgendaGuardianService
from app.services.account_registry import AccountRecord
from app.services.assistant_context_service import AssistantContextService
from app.services.assistant_reply_service import AssistantReplyService
from app.services.automation_service import AutomationService
from app.services.deepseek_service import DeepSeekService
from app.services.groq_service import GroqChatService
from app.services.memory_job_service import MemoryJobService
from app.services.memory_service import MemoryAnalysisService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.proactive_assistant_service import ProactiveAssistantService
from app.services.banco_de_dados_local_store import BancoDeDadosLocalStore
from app.services.whatsapp_agent_service import WhatsAppAgentService


@dataclass(slots=True)
class ServiceBundle:
    account: AccountRecord
    settings: Settings
    store: BancoDeDadosLocalStore
    observer_gateway: ObserverGatewayService
    agent_gateway: WhatsAppAgentGatewayService
    deepseek_service: DeepSeekService
    groq_service: GroqChatService
    assistant_context_service: AssistantContextService
    assistant_reply_service: AssistantReplyService
    memory_service: MemoryAnalysisService
    memory_job_service: MemoryJobService
    automation_service: AutomationService
    whatsapp_agent_service: WhatsAppAgentService
    agenda_guardian_service: AgendaGuardianService
    proactive_assistant_service: ProactiveAssistantService


class ServiceBundleCache:
    def __init__(self, *, base_settings: Settings) -> None:
        self.base_settings = base_settings
        self._lock = threading.RLock()
        self._bundles: dict[str, ServiceBundle] = {}
        self._warmed_accounts: set[str] = set()

    def get_bundle(self, account: AccountRecord) -> ServiceBundle:
        cache_key = str(account.app_user_id)
        with self._lock:
            existing = self._bundles.get(cache_key)
            if existing is not None and existing.account.db_path == account.db_path:
                return existing

            scoped_settings = self.base_settings.model_copy(
                update={
                    "database_path": account.db_path,
                    "default_user_id": account.app_user_id,
                }
            )
            store = BancoDeDadosLocalStore(
                database_path=account.db_path,
                default_user_id=account.app_user_id,
                message_retention_max_rows=min(
                    scoped_settings.message_retention_max_rows,
                    scoped_settings.memory_analysis_max_messages,
                ),
                first_analysis_queue_limit=min(
                    scoped_settings.memory_first_analysis_max_messages,
                    scoped_settings.memory_analysis_max_messages,
                ),
            )
            observer_gateway = ObserverGatewayService(
                settings=scoped_settings,
                account_user_id=str(account.app_user_id),
                account_username=account.username,
            )
            agent_gateway = WhatsAppAgentGatewayService(
                settings=scoped_settings,
            )
            deepseek_service = DeepSeekService(settings=scoped_settings)
            groq_service = GroqChatService(settings=scoped_settings)
            assistant_context_service = AssistantContextService(
                settings=scoped_settings,
                store=store,
                deepseek_service=deepseek_service,
            )
            assistant_reply_service = AssistantReplyService(
                settings=scoped_settings,
                store=store,
                deepseek_service=deepseek_service,
                groq_service=groq_service,
                context_service=assistant_context_service,
            )
            memory_service = MemoryAnalysisService(
                settings=scoped_settings,
                store=store,
                deepseek_service=deepseek_service,
                groq_service=groq_service,
            )
            memory_job_service = MemoryJobService(
                settings=scoped_settings,
                store=store,
                memory_service=memory_service,
            )
            automation_service = AutomationService(
                settings=scoped_settings,
                store=store,
                memory_service=memory_service,
            )
            agenda_guardian_service = AgendaGuardianService(
                settings=scoped_settings,
                store=store,
                deepseek_service=deepseek_service,
                observer_gateway=observer_gateway,
                agent_gateway=agent_gateway,
            )
            proactive_assistant_service = ProactiveAssistantService(
                settings=scoped_settings,
                store=store,
                deepseek_service=deepseek_service,
                observer_gateway=observer_gateway,
                agent_gateway=agent_gateway,
            )
            whatsapp_agent_service = WhatsAppAgentService(
                settings=scoped_settings,
                store=store,
                reply_service=assistant_reply_service,
                deepseek_service=deepseek_service,
                groq_service=groq_service,
                observer_gateway=observer_gateway,
                agent_gateway=agent_gateway,
                agenda_guardian_service=agenda_guardian_service,
                proactive_assistant_service=proactive_assistant_service,
            )
            bundle = ServiceBundle(
                account=account,
                settings=scoped_settings,
                store=store,
                observer_gateway=observer_gateway,
                agent_gateway=agent_gateway,
                deepseek_service=deepseek_service,
                groq_service=groq_service,
                assistant_context_service=assistant_context_service,
                assistant_reply_service=assistant_reply_service,
                memory_service=memory_service,
                memory_job_service=memory_job_service,
                automation_service=automation_service,
                whatsapp_agent_service=whatsapp_agent_service,
                agenda_guardian_service=agenda_guardian_service,
                proactive_assistant_service=proactive_assistant_service,
            )
            self._bundles[cache_key] = bundle
            return bundle

    def warm_bundle(self, account: AccountRecord) -> ServiceBundle:
        bundle = self.get_bundle(account)
        cache_key = str(account.app_user_id)
        with self._lock:
            if cache_key in self._warmed_accounts:
                return bundle
            bundle.automation_service.warm_start()
            bundle.agenda_guardian_service.warm_start()
            bundle.proactive_assistant_service.warm_start()
            self._warmed_accounts.add(cache_key)
        return bundle
