# Backend Architecture

## Estrutura de Diretórios

```
backend/
  app/
    main.py              — FastAPI app, CORS, routers, exception handlers
    config.py            — Settings (pydantic-settings), todas as variaveis
    schemas.py           — Todos os Pydantic models de request/response
    dependencies.py      — Deps do FastAPI (settings, db, auth)
    routers/
      agenda.py          — Eventos, lembretes, conflitos
      auth.py            — Firebase Auth, registro de contas
      automation.py      — Automacao de analise/refinamento
      chat.py            — Chat com contexto de memoria
      global_agent.py    — Agente global (multi-conta)
      internal_accounts.py — Gerenciamento de contas internas
      internal_agent.py  — API interna do agente WhatsApp
      internal.py        — API interna (observer ingest, session keys)
      internal_storage.py — Storage interno
      memories.py        — CRUD de memoria (persona, snapshots, projetos, pessoas)
      observer.py        — Status do observer, sync, QR
      whatsapp_agent.py  — Agente WhatsApp (threads, sessoes, mensagens)
    services/
      account_registry.py      — Registro de contas no sistema
      agenda_guardian_service.py — Lembretes e deteccao de conflitos
      assistant_context_service.py — Montagem de contexto para LLM
      assistant_reply_service.py  — Geracao de respostas do assistente
      automation_service.py      — Automacao (sync → analyze → refine)
      chat_service.py            — Chat com Groq/DeepSeek
      deepseek_service.py        — Cliente DeepSeek (analise de memoria)
      firebase_auth.py           — Verificacao de tokens Firebase
      groq_service.py            — Cliente Groq (chat)
      memory_job_service.py      — Execucao de jobs de analise
      memory_service.py          — Analise de memoria (principal)
      observer_gateway.py        — Comunicacao com WhatsApp gateway
      service_bundle.py          — Bundle de servicos compartilhados
      sqlite_client.py           — Cliente SQLite + migracoes
      sqlite_schema.sql          — Schema completo do banco
      banco_de_dados_local_store.py          — Fallback Banco_de_dados_local + migracoes locais
      whatsapp_agent_service.py  — Logica do agente WhatsApp
```

## Routers Registrados (ordem importa para matching)

1. `auth` — `/api/auth/*`
2. `agenda` — `/api/agenda/*`
3. `observer` — `/api/observer/*`
4. `global_agent` — `/api/global-agent/*`
5. `memories` — `/api/memories/*`
6. `chat` — `/api/chat/*`
7. `automation` — `/api/automation/*`
8. `internal_accounts` — `/api/internal/accounts/*`
9. `internal` — `/api/internal/*`
10. `internal_agent` — `/api/internal/agent/*`
11. `internal_storage` — `/api/internal/storage/*`
12. `whatsapp_agent` — `/api/whatsapp-agent/*`

## Settings Principais (`config.py`)

| Categoria | Variaveis |
|-----------|-----------|
| DB | `AURACORE_DB_PATH`, `AURACORE_DB_ROOT` |
| Gateway | `WHATSAPP_GATEWAY_URL`, `INTERNAL_API_TOKEN` |
| LLM | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL` |
| Memoria | `MEMORY_ANALYSIS_MAX_MESSAGES=160`, `MEMORY_FIRST_ANALYSIS_MAX_MESSAGES=120`, `MEMORY_INCREMENTAL_MIN_MESSAGES=20` |
| Chat | `CHAT_MAX_HISTORY_MESSAGES=18`, `CHAT_CONTEXT_CHARS=18000` |
| Retencao | `MESSAGE_RETENTION_MAX_ROWS=160` |
| Agente | `WHATSAPP_AGENT_IDLE_TIMEOUT_MINUTES=10` |

## Schemas Principais

- **Observer**: `ObserverStatusResponse`, `ObserverMessageRefreshResponse`
- **WhatsApp Agent**: `WhatsAppAgentStatusResponse`, `WhatsAppAgentWorkspaceResponse`, `WhatsAppAgentThreadResponse`, `WhatsAppAgentMessageResponse`, `WhatsAppAgentContactMemoryResponse`
- **Memoria**: `MemoryCurrentResponse`, `MemorySnapshotResponse`, `ProjectMemoryResponse`, `PersonMemoryResponse`, `AnalyzeMemoryResponse`, `RefineMemoryResponse`
- **Automacao**: `AutomationSettingsResponse`, `AnalysisJobResponse`, `AutomationDecisionResponse`, `WhatsAppSyncRunResponse`, `ModelRunResponse`
- **Chat**: `ChatSessionResponse`, `ChatThreadResponse`, `ChatWorkspaceResponse`
- **Agenda**: `AgendaEventResponse`, `AgendaConflictResponse`
- **Auth**: `AuthenticatedAccountResponse`, `RegisterAccountRequest`
- **Global Agent**: `GlobalAgentStatusResponse`, `ActiveAccountResponse`

## Exception Handlers

| Excecao | HTTP Status |
|---------|-------------|
| `DeepSeekError` | 502 |
| `GroqChatError` | 502 |
| `ChatServiceError` | 400 |
| `MemoryAnalysisError` | 400 |
