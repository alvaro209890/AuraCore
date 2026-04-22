# Project Memory

## Identidade do projeto

- Repositório principal: `AuraCore`
- Branch principal usada em produção: `main`
- Backend em produção local roda a partir do runtime em `/home/server/.local/share/auracore-runtime/repo/backend`
- Repositório principal fica em `/media/server/HD Backup/Servidores_NAO_MEXA/AuraCore`
- Stack atual do repositório:
  - `backend`: FastAPI + SQLite local com `BancoDeDadosLocalStore` próprio sobre `sqlite3`
  - `frontend`: Next.js 15 para o dashboard principal autenticado
  - `agent-frontend`: Next.js 15 separado para o dashboard do agente global
  - `whatsapp-gateway`: Express + Baileys para observer e agent
- Os frontends têm entrada mínima em `app/page.tsx`; a maior parte da UI está concentrada em `frontend/components/connection-dashboard.tsx` e `agent-frontend/components/global-agent-dashboard.tsx`
- No frontend principal, o `connection-dashboard.tsx` passou a importar abas modulares em `frontend/components/dashboard/tabs/`, mas ainda concentra helpers compartilhados e orquestração de estado
- As abas `Agenda`, `Automação` e `Proatividade` do frontend principal agora compartilham uma linguagem visual e controles próprios via classes `ops-*` em `frontend/app/globals.css`, mantendo o mesmo tema escuro do restante do dashboard
- As abas `Automação` e `Proatividade` agora usam painéis operacionais, shells escuros para `input/select/time/number`, botões próprios `ops-hero-button` e seletores segmentados no mesmo kit visual `ops-*`
- O frontend principal nao usa Tailwind; quando surgirem classes utilitarias estilo `bg-white`, `rounded-xl`, `p-6` ou similares, elas so funcionam se houver CSS proprio cobrindo isso em `frontend/app/globals.css`
- Os helpers compartilhados do dashboard (`ModernStatCard`, `MemorySignalCard`, `SignalBlock`, `StatusLine`, `ManualInfoCard`, `ManualStep`, `ProjectInfoBlock`) dependem das classes dedicadas já definidas em `frontend/app/globals.css`; se voltarem a usar utilitarios crus, cards e textos podem quebrar em varias abas
- A maior parte da lógica de domínio do backend está concentrada em `backend/app/services/banco_de_dados_local_store.py`, `memory_service.py`, `whatsapp_agent_service.py`, `agenda_guardian_service.py` e `deepseek_service.py`

## WhatsApp Agent

- O modo CLI do WhatsApp foi removido em abril/2026; `/agente`, `/fechar` e afins não têm mais semântica de terminal
- O `agent-frontend` no segundo site do Firebase é o único painel para gerenciar QR/reset do número global do agente
- Chat e proatividade sempre saem pelo canal global `agent`; o `observer` serve para identificar a conta correta pelo número do owner
- O agente do WhatsApp agora só responde ao número salvo como `observer_owner_phone` de uma conta ativa; contatos conhecidos e admins legados não autorizam resposta
- As respostas conversacionais do WhatsApp agora usam Groq no backend; o modelo padrão dedicado do canal foi trocado para `llama-3.3-70b-versatile`
- Quando mudanças do backend são feitas, normalmente é preciso sincronizar runtime e repositório principal antes de commitar
- O agente conversacional do WhatsApp é majoritariamente reativo: hoje ele responde mensagens recebidas, usa memória própria por contato e tem proatividade nativa principalmente para agenda (conflitos e lembretes)
- Já existe base de dados para evoluir proatividade mais rica: `whatsapp_agent_contact_memories`, `important_messages`, `analysis_jobs`, `automation_decisions` e snapshots/projetos da memória geral do usuário
- Em abril/2026 foi introduzido um subsistema dedicado de proatividade do WhatsApp: `ProactiveAssistantService`, com preferências persistidas, candidatos proativos, log de entregas e digests de manhã/noite
- A proatividade do WhatsApp agora também compõe a mensagem final com contexto do dono (perfil, tom preferido, sinais recentes e ações implícitas) via `DeepSeekService.generate_proactive_message`, com fallback heurístico local caso o modelo falhe
- O roteamento inbound do agente global resolve a conta por `observer_owner_phone`; no outbound, `ProactiveAssistantService` e `agenda_guardian_service` usam somente o owner do `observer` da conta atual como alvo lógico
- Em abril/2026 o outbound proativo passou a preferir o thread mais recente do WhatsApp Agent para definir `chat_jid`/telefone do dono; isso é importante para contatos em formato `@lid` e evita cair num owner genérico do observer quando já existe conversa recente no agente
- O WhatsApp Agent agora suporta comandos diretos do owner para projetos: criar projeto manual, marcar como concluído, reabrir e pedir um plano curto, inclusive quando a resposta vier em cima de um `project_nudge` recente
- As respostas do WhatsApp agora podem receber um contexto prioritário curto vindo do candidato proativo recente; isso evita perder o fio em respostas ambíguas como "marque isso como concluído" ou "me dá um plano"

## Deploy local

- Serviço principal do backend: `auracore-backend.service` no `systemctl --user`
- O backend costuma ser validado por:
  - `python3 -m py_compile` nos arquivos alterados
  - `curl https://api.cursar.space/api/global-agent/status`
  - `curl https://api.cursar.space/api/global-agent/admin-contacts`

## Convenção operacional

- Não reverter mudanças do usuário sem instrução explícita
- Se alterar comportamento do backend em produção, reiniciar o backend local e validar o estado após o restart
- Registrar aqui só fatos estáveis; contexto recente vai em `active-context.md`

## Memória e contexto

- O contexto de resposta do Orion agora prioriza carregamento sob demanda: projetos, snapshots e memória do contato entram no prompt apenas quando o planner indicar necessidade real
- Mensagens simples/curtas podem pular a etapa de `assistant_search_plan` e cair direto no fallback heurístico para reduzir custo e latência
- O pipeline `improve_memory` usa um contexto próprio mais enxuto que o da `first_analysis`, para reduzir tokens nos lotes automáticos sem mexer no bootstrap inicial
- O frontend principal agora normaliza respostas de `ProjectMemory` em `frontend/lib/api.ts` antes de renderizar; isso evita que campos nulos/legados em `stage`, `priority`, `status`, `aliases`, `blockers`, `next_steps` e `evidence` derrubem o dashboard
- Em abril/2026 o incremental de memória passou a selecionar só projetos relacionados ao lote atual e tentar merge local de projetos antes de recorrer ao DeepSeek; isso reduz custo fixo e evita chamada extra do modelo em matches claros
- Em abril/2026 o `automation_service` passou a preferir `plan_next_batch()` também nos jobs incrementais automáticos e no backlog drain; isso reduz custo de DeepSeek porque a execução real usa lote fixo de mensagens pendentes em vez de reler a janela automática larga
- O merge incremental de projetos pode ser pulado quando o lote novo não trouxe candidatos de projeto; nesse caso os projetos existentes são preservados sem nova chamada ao modelo
- O `refine_saved_memory` agora usa contexto dedicado mais compacto que o prompt padrão de análise e seleciona só os contatos mais relevantes para refinamento, evitando mandar todo o bloco salvo de contatos ao DeepSeek sem necessidade
- A extração de `active_projects` agora combina prompt mais rígido no `deepseek_service` com refinamento local em `memory_service`, enriquecendo resumo/evidências/próximos passos a partir das mensagens-fonte e descartando projetos vagos
- A tabela `project_memories` agora persiste também `aliases`, `stage`, `priority`, `blockers`, `confidence_score` e `last_material_update_at`; backend e dashboard principal já expõem esses campos
- Em abril/2026 o `assistant_context_service` ganhou um caminho `structured-first` para intents de agenda e projetos: ele monta blocos compactos diretamente da agenda e de `project_memories` antes de recorrer a snapshots e contexto amplo
- A tabela `project_memories` agora persiste `origin_source` (`memory` ou `manual`), o que permite preservar projetos criados manualmente na UI sem perdê-los em merges futuros
- A agenda usa uma tabela unica para eventos automáticos e manuais; eventos criados manualmente entram em `agenda` com `message_id` sintético no formato `manual:{uuid}` e participam de conflito/lembrete igual aos demais
- O `DeepSeekAssistantSearchPlan` do backend agora suporta também `important_message_queries` e `important_messages_limit`, alinhando o fluxo DeepSeek com a infraestrutura já existente de `important_messages`
- O aprendizado do WhatsApp pode persistir `important_messages` direto do `extract_agent_memory`, usando a mesma rodada do modelo para classificar relevância global sem abrir outro pipeline paralelo
- Os metadados de aprendizado do WhatsApp agora preservam também `agent_writing_style_hints`; a proatividade usa isso junto do `preferred_tone` para ajustar o jeito do nudge soar mais natural para o dono
- A proatividade de projetos agora pode enriquecer `project_nudge` com `suggested_actions` geradas pelo DeepSeek, com fallback heurístico local quando o modelo falhar
- O `ProactiveAssistantService` agora usa `important_messages` para semear followups prioritários, escolhe o melhor candidato devido por score antes de interromper o dono e passou a enriquecer digests com foco de projeto além do radar de agenda/pendências
- O `agenda_guardian_service` agora consegue calcular slots livres locais para sugerir alternativas em conflitos de agenda
- O `automation_service` agora respeita `auto_sync_enabled` para o loop automático de ingest/sync, usa `default_detail_mode`, `default_target_message_count` e `default_lookback_hours` nos lotes incrementais automáticos e pode enfileirar `refine_saved` automático quando `auto_refine_enabled` estiver ligado e o backlog imediato acabar
- Na proatividade, `followup`, `routine`, `project_nudge` e os digests têm produtores reais no `ProactiveAssistantService`; a UI deixou de expor `Agenda` como categoria proativa e o cooldown mínimo passou a olhar apenas entregas `sent`, enquanto os lembretes formais continuam no `agenda_guardian_service`
- Os defaults de proatividade ficaram mais agressivos para novas contas: `intensity=high`, `max_unsolicited_per_day=6` e `min_interval_minutes=45`
- A aba `Agenda` agora usa shells visuais `ops-*` e botões/pills do dashboard para criação e edição, com status em pills e presets de lembrete em vez de campos crus e `select` simples
- A aba `Memória` do frontend principal usa `memoryActivity` como fonte primária para pipeline, jobs, syncs e decisões recentes; `automationStatus` fica como fallback quando esse snapshot específico não vier carregado
- O backend de agenda agora expõe endpoints para consulta textual e confirmação pendente (`POST /api/agenda/query`, `GET /api/agenda/pending-confirmation`, `POST /api/agenda/pending-confirmation/resolve`) e a agenda manual já persiste `recurrence_rule`/`excluded_dates`
- O canal conversacional do WhatsApp usa Groq via `WHATSAPP_AGENT_GROQ_MODEL`; a transcrição de áudio do observer/agente também usa Groq e agora aceita configuração explícita por `GROQ_TRANSCRIPTION_MODEL` e `GROQ_TRANSCRIPTION_FALLBACK_MODEL`
- A proatividade do WhatsApp agora considera atividade inbound muito recente do dono antes de enviar novo nudge e entende mais pistas de prazo em followups (`daqui a X`, dia da semana, manhã/tarde/noite), reduzindo interrupção ruim e melhorando o timing do radar
