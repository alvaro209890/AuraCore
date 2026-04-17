# Project Memory

## Identidade do projeto

- Repositório principal: `AuraCore`
- Branch principal usada em produção: `main`
- Backend em produção local roda a partir do runtime em `/home/server/.local/share/auracore-runtime/repo/backend`
- Repositório principal fica em `/media/server/HD Backup/Servidores_NAO_MEXA/AuraCore`
- Stack atual do repositório:
  - `backend`: FastAPI + SQLite local com `SupabaseStore` próprio sobre `sqlite3`
  - `frontend`: Next.js 15 para o dashboard principal autenticado
  - `agent-frontend`: Next.js 15 separado para o dashboard do agente global
  - `whatsapp-gateway`: Express + Baileys para observer e agent
- Os frontends têm entrada mínima em `app/page.tsx`; a maior parte da UI está concentrada em `frontend/components/connection-dashboard.tsx` e `agent-frontend/components/global-agent-dashboard.tsx`
- No frontend principal, o `connection-dashboard.tsx` passou a importar abas modulares em `frontend/components/dashboard/tabs/`, mas ainda concentra helpers compartilhados e orquestração de estado
- A maior parte da lógica de domínio do backend está concentrada em `backend/app/services/supabase_store.py`, `memory_service.py`, `whatsapp_agent_service.py`, `agenda_guardian_service.py` e `deepseek_service.py`

## WhatsApp Agent / CLI

- Existe um modo agente/CLI do WhatsApp para o Álvaro
- O Álvaro (`6684396232`) deve ser tratado como admin no fluxo do agente
- O backend já suporta sessão terminal persistida, contexto CLI, progresso intermediário e mensagem final de conclusão
- Quando mudanças do backend são feitas, normalmente é preciso sincronizar runtime e repositório principal antes de commitar
- O agente conversacional do WhatsApp é majoritariamente reativo: hoje ele responde mensagens recebidas, usa memória própria por contato e tem proatividade nativa principalmente para agenda (conflitos e lembretes)
- Já existe base de dados para evoluir proatividade mais rica: `whatsapp_agent_contact_memories`, `important_messages`, `analysis_jobs`, `automation_decisions` e snapshots/projetos da memória geral do usuário
- Em abril/2026 foi introduzido um subsistema dedicado de proatividade do WhatsApp: `ProactiveAssistantService`, com preferências persistidas, candidatos proativos, log de entregas e digests de manhã/noite

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
- O merge incremental de projetos pode ser pulado quando o lote novo não trouxe candidatos de projeto; nesse caso os projetos existentes são preservados sem nova chamada ao modelo
- Em abril/2026 o `assistant_context_service` ganhou um caminho `structured-first` para intents de agenda e projetos: ele monta blocos compactos diretamente da agenda e de `project_memories` antes de recorrer a snapshots e contexto amplo
- A tabela `project_memories` agora persiste `origin_source` (`memory` ou `manual`), o que permite preservar projetos criados manualmente na UI sem perdê-los em merges futuros
- A agenda usa uma tabela unica para eventos automáticos e manuais; eventos criados manualmente entram em `agenda` com `message_id` sintético no formato `manual:{uuid}` e participam de conflito/lembrete igual aos demais
- O `DeepSeekAssistantSearchPlan` do backend agora suporta também `important_message_queries` e `important_messages_limit`, alinhando o fluxo DeepSeek com a infraestrutura já existente de `important_messages`
- O aprendizado do WhatsApp pode persistir `important_messages` direto do `extract_agent_memory`, usando a mesma rodada do modelo para classificar relevância global sem abrir outro pipeline paralelo
- A proatividade de projetos agora pode enriquecer `project_nudge` com `suggested_actions` geradas pelo DeepSeek, com fallback heurístico local quando o modelo falhar
- O `agenda_guardian_service` agora consegue calcular slots livres locais para sugerir alternativas em conflitos de agenda
