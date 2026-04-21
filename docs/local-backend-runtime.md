# Backend Local do AuraCore

Este documento descreve como o backend local desta máquina está executando em produção, como o observador do WhatsApp entra no fluxo e como o SQLite local sustenta o sistema.

## Topologia local

- Repositório: `/home/acer/Downloads/AuraCore`
- Backend FastAPI: `127.0.0.1:8000`
- WhatsApp gateway: `127.0.0.1:10001`
- Túnel público: `https://api.cursar.space`
- Frontend publicado: `https://auracore-82bf2.web.app`
- Banco SQLite local: `/home/acer/Documentos/Bando_de_dados/Aura_Core/sqlite/auracore.sqlite3`

Estrutura local preparada no disco:

- `/home/acer/Documentos/Bando_de_dados/Aura_Core/sqlite`
- `/home/acer/Documentos/Bando_de_dados/Aura_Core/backups`
- `/home/acer/Documentos/Bando_de_dados/Aura_Core/exports`

## Subida do backend nesta máquina

O backend local é executado por `systemd --user`.

Arquivos envolvidos:

- [`deploy/systemd-user/auracore-backend.service`](/home/acer/Downloads/AuraCore/deploy/systemd-user/auracore-backend.service)
- [`scripts/run-backend-prod.sh`](/home/acer/Downloads/AuraCore/scripts/run-backend-prod.sh)
- [`backend/.env`](/home/acer/Downloads/AuraCore/backend/.env)

Fluxo:

1. O `systemd --user` carrega `backend/.env`.
2. O serviço chama `scripts/run-backend-prod.sh`.
3. O script entra em `backend/`, injeta `backend/.vendor` no `PYTHONPATH` e sobe `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. O Cloudflare Tunnel publica essa API local em `https://api.cursar.space`.

## Boot automático

Os serviços locais sobem com o usuário `acer` no boot:

- `auracore-backend.service`
- `auracore-whatsapp-gateway.service`
- `auracore-cloudflared.service`
- `auracore-auto-update.timer`

Instalação das units:

- [`scripts/install-user-services.sh`](/home/acer/Downloads/AuraCore/scripts/install-user-services.sh)

Pré-requisito de boot sem login manual:

- `loginctl enable-linger acer`

Com `linger` ativo, o stack sobe mesmo sem abrir sessão gráfica.

## Auto-update do GitHub

Arquivos envolvidos:

- [`scripts/auto-update.sh`](/home/acer/Downloads/AuraCore/scripts/auto-update.sh)
- [`deploy/systemd-user/auracore-auto-update.service`](/home/acer/Downloads/AuraCore/deploy/systemd-user/auracore-auto-update.service)
- [`deploy/systemd-user/auracore-auto-update.timer`](/home/acer/Downloads/AuraCore/deploy/systemd-user/auracore-auto-update.timer)

Comportamento:

- Verifica `origin/main` a cada 2 minutos.
- Executa `git pull --ff-only` quando encontra commit novo.
- Reinstala units e reinicia backend, gateway e cloudflared quando necessário.
- Não sobrescreve alterações locais rastreadas: se a árvore Git estiver suja, a atualização automática é pulada.

## Fluxo do observador do WhatsApp

Serviços e arquivos principais:

- [`whatsapp-gateway/src/server.ts`](/home/acer/Downloads/AuraCore/whatsapp-gateway/src/server.ts)
- [`whatsapp-gateway/src/whatsapp.ts`](/home/acer/Downloads/AuraCore/whatsapp-gateway/src/whatsapp.ts)
- [`backend/app/routers/internal.py`](/home/acer/Downloads/AuraCore/backend/app/routers/internal.py)
- [`backend/app/services/automation_service.py`](/home/acer/Downloads/AuraCore/backend/app/services/automation_service.py)
- [`backend/app/services/memory_service.py`](/home/acer/Downloads/AuraCore/backend/app/services/memory_service.py)

Fluxo operacional atualizado:

1. O canal `observer` conecta pelo QR.
2. O gateway liga com `syncFullHistory` para o observador.
3. O histórico e as mensagens novas entram pelo endpoint interno `/api/internal/observer/messages/ingest`.
4. O backend salva apenas chats diretos com texto útil e ignora grupo, status, mídias sem texto e duplicatas.
5. Antes da primeira memória existir, a fila operacional é mantida no máximo com as 120 mensagens mais recentes (`MEMORY_FIRST_ANALYSIS_MAX_MESSAGES`, limitado também por `MEMORY_ANALYSIS_MAX_MESSAGES`).
6. Quando a sincronização assenta, o backend fecha automaticamente o `wa_sync_run`.
7. Se ainda não houver memória inicial, ele monta a primeira análise a partir das mensagens pendentes mais recentes e balanceadas, até o limite de 120.
8. Depois da primeira análise, o backend marca um `observer_history_cutoff_at` e deixa o backlog antigo fora do fluxo incremental.
9. A partir daí, novas mensagens entram em tempo real e, quando a fila atinge o limiar incremental, o backend enfileira automaticamente o próximo lote econômico.

Na prática, o comportamento esperado agora é:

- Re-vinculou o observador: o backend puxa o histórico recente, guarda até 120 mensagens operacionais para a primeira leitura e dispara a primeira análise sozinho.
- Depois disso, mensagens novas continuam chegando por `messages.upsert`.
- Quando houver volume suficiente, o backend roda a atualização incremental sozinho.

## Estrutura do banco SQLite local

Schema base:

- [`backend/app/services/sqlite_schema.sql`](/home/acer/Downloads/AuraCore/backend/app/services/sqlite_schema.sql)

Migrações locais não destrutivas:

- [`backend/app/services/banco_de_dados_local_store.py`](/home/acer/Downloads/AuraCore/backend/app/services/banco_de_dados_local_store.py)
- [`backend/app/services/sqlite_client.py`](/home/acer/Downloads/AuraCore/backend/app/services/sqlite_client.py)

### Tabelas centrais do observador e memória

- `mensagens`
  Guarda a fila operacional das mensagens diretas do observador.
  Colunas-chave: `id`, `chat_jid`, `contact_phone`, `message_text`, `timestamp`, `embedding`, `ingested_at`, `analysis_status`, `analysis_job_id`, `analysis_started_at`, `analyzed_at`.

- `processed_message_ids`
  Guarda IDs já consolidados para evitar reprocessamento depois que o lote foi absorvido na memória.

- `whatsapp_known_contacts`
  Mantém nome normalizado, origem do nome e vínculo entre `contact_phone` e `chat_jid`.

- `persona`
  Estado consolidado da memória do dono.
  Colunas-chave: `life_summary`, `last_analyzed_at`, `last_snapshot_id`, contadores de retenção e listas estruturais.

- `memory_snapshots`
  Snapshots analíticos gerados pelo reasoner a cada leitura.

- `person_memories`
  Memória consolidada por contato/pessoa.

- `person_memory_snapshots`
  Histórico por pessoa derivado dos snapshots.

- `project_memories`
  Projetos ativos inferidos pela análise.
  Inclui `what_is_being_built`, `built_for`, `next_steps` e `evidence`.

- `important_messages`
  Mensagens duráveis salvas após extração de importância.

### Tabelas do agente WhatsApp

- `whatsapp_agent_settings`
  Configuração do auto-reply do agente.

- `whatsapp_agent_threads`
  Conversas do agente por contato.

- `whatsapp_agent_thread_sessions`
  Sessões temporais de atendimento.

- `whatsapp_agent_messages`
  Mensagens trocadas pelo agente, estados de processamento e latência.

- `whatsapp_agent_contact_memories`
  Memória específica de cada contato atendido pelo agente.

### Tabelas de retenção e automação

- `message_retention_state`
  Guarda contadores globais de ingestão/prune e o `observer_history_cutoff_at`.

- `automation_settings`
  Configurações da automação: análise automática, limiar de novas mensagens, orçamento diário e teto de jobs.

- `wa_sync_runs`
  Registro de cada ciclo de sincronização do WhatsApp.
  Colunas-chave: `trigger`, `status`, `messages_seen_count`, `messages_saved_count`, `messages_ignored_count`, `messages_pruned_count`, `baseline_ingested_count`, `baseline_pruned_count`, `last_activity_at`.

- `automation_decisions`
  Decisões tomadas pela automação para enfileirar ou não uma análise.

- `analysis_jobs`
  Jobs de análise/refinamento com estimativa de custo e tokens.

- `analysis_job_messages`
  Relação entre um job e as mensagens efetivamente usadas.

- `model_runs`
  Histórico das chamadas de modelo, custo estimado, latência e sucesso/erro.

### Tabelas de sessão do WhatsApp

- `wa_sessions`
  Credenciais principais da sessão do Baileys.

- `wa_session_keys`
  Chaves auxiliares da sessão do Baileys.

Essas duas tabelas permitem que o QR permaneça vinculado entre reinícios, desde que a sessão continue válida no WhatsApp.

## Compatibilidade e migração local

No startup, o backend aplica migrações locais não destrutivas para colunas que possam estar faltando em bancos legados desta máquina. Isso inclui:

- `mensagens.embedding`
- colunas de análise em `mensagens`
- contadores estruturais em `persona`
- colunas de contexto em `project_memories`
- `observer_history_cutoff_at` em `message_retention_state`

Essas migrações evitam quebrar o backend quando o código sobe com schema mais novo do que o SQLite existente.

## Operação diária

Com o estado atual:

- ao ligar o PC, backend, gateway e túnel sobem sozinhos;
- quando entra commit novo na `main`, o PC atualiza e reinicia os serviços;
- quando o observador é vinculado por QR, o sistema inicia a ingestão histórica;
- a primeira análise usa até 120 mensagens recentes;
- depois disso, o backend segue processando as mensagens novas automaticamente.
