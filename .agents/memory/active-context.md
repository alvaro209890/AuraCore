# Active Context

## Estado operacional recente

- O WhatsApp CLI recebeu várias melhorias recentes para ficar mais próximo de uma CLI real
- Já existe:
  - parsing mais tolerante do planner da CLI
  - fallback heurístico para análise de pastas como `Downloads`
  - progresso intermediário no WhatsApp
  - mensagem final explícita avisando que a solicitação terminou
  - edição estruturada por trecho (`edit`)
  - validação automática pós-alteração quando aplicável

## Diagnóstico recente importante

- Um erro real do Álvaro ocorreu porque o `cli_plan` do DeepSeek voltou com JSON inválido
- Isso foi mitigado em duas camadas:
  - recuperação do plano por texto cru no parser
  - fallback heurístico local para pedidos de análise de pasta/repositório
- Outro erro real ocorreu na sessão `Analise a pasta de dowloads desse pc`
- Causa observada em produção:
  - o typo `dowloads` ainda não era reconhecido como pedido de `Downloads`
  - o planner acabou emitindo `cd ..`
  - o backend tratava `cd ..` como caminho literal `.../cd ..`, em vez de interpretar o alvo `..`
- Correção aplicada:
  - novos aliases comuns de typo para `Downloads`
  - parsing de alvo primário para ferramentas como `cd`, `write` e `edit`
  - wrappers seguros como `bash -lc 'ls -la'` e `bash -lc 'find . -maxdepth 2'` agora contam como autonomia segura e não pedem confirmação

## Uso futuro desta pasta

- Atualizar este arquivo quando houver:
  - correção recente relevante
  - mudança de deploy
  - comportamento quebrado observado em produção
  - decisão operacional importante para o próximo agente

## Limpeza

- Quando este arquivo crescer demais, resumir e manter apenas o contexto operacional realmente útil

## Atualização 2026-04-15

- Bot do WhatsApp agora só responde contatos pré-cadastrados ou o owner
- Antes: `upsert_known_contact` registrava todo mundo antes de checar, o bot respondia qualquer um
- Agora: `get_known_contact_by_phone` roda primeiro; se o contato não existe e não é owner/admin → `ignored_unknown_contact`
- Backend reiniciado e rodando via Cloudflare tunnel (api.cursar.space)
- Commit `ebcafb8` pushado no main

## Atualização recente

- Abril/2026: o fluxo de memória do Orion foi enxugado para gastar menos tokens
- Ajustes aplicados:
  - `assistant_context_service` agora evita buscar snapshots/projetos por padrão e só injeta memória do contato quando o planner pedir
  - mensagens curtas e diretas podem pular o `assistant_search_plan`
  - `memory_service` passou a compactar mais o contexto padrão de análise/refino antes de chamar o modelo
  - no incremental automático (`improve_memory`), o contexto agora é menor que o da primeira análise e o merge de projetos é pulado quando não há candidatos novos

## Atualização 2026-04-17

- Revisão arquitetural do sistema confirmou que o agente principal do WhatsApp ainda não executa campanhas ou sugestões proativas fora do fluxo reativo de entrada
- Proatividade real existente hoje:
  - lembretes e avisos de conflito da `agenda_guardian_service`
  - respostas com memória do contato quando a mensagem atual justifica carregar esse contexto
- Lacunas confirmadas para evolução:
  - `important_messages` existe no store, mas não está integrado ao pipeline atual de resposta do `whatsapp_agent_service`
  - a memória própria do contato é aprendida por mensagem e usada como contexto, mas ainda não há scoring de momento certo para enviar sugestões espontâneas
  - a base já possui `analysis_jobs` e `automation_decisions`, o que favorece implementar um orquestrador de nudge/proatividade sem reinventar a infraestrutura

## Atualização 2026-04-17 2

- Implementado v1 do motor de proatividade do WhatsApp
- Backend:
  - novo `ProactiveAssistantService` roda em loop próprio no `warm_start`
  - captura mensagens do owner para inferir follow-ups, rotina e nudges de projeto
  - responde a confirmações/dispensas do owner sobre candidatos proativos
  - registra outbound proativo no mesmo histórico do agente com `generated_by=proactive_assistant`
- Persistência nova no SQLite:
  - `important_messages`
  - `proactive_preferences`
  - `proactive_candidates`
  - `proactive_delivery_log`
  - `proactive_digest_state`
- API nova em `/api/whatsapp-agent/proactivity/*` para settings, candidatos, deliveries e tick manual
- Dashboard ganhou aba de Proatividade com configuração, fila ativa e histórico recente
- Validação local concluída:
  - `python3 -m py_compile` dos arquivos backend alterados
  - `npm run build` no frontend
- Pendência operacional antes de considerar pronto em runtime:
  - aplicar migração/boot do backend em produção local e validar envio real de nudge/digest após restart

## Atualização 2026-04-17 3

- Análise estrutural do repositório confirmou alguns pontos práticos para próximos agentes:
  - não apareceu suíte de testes rastreável em `backend`, `frontend`, `agent-frontend` ou `whatsapp-gateway`
  - o repositório versiona artefatos de build e dependências locais como `.next`, `out`, `dist` e `node_modules`
  - há forte concentração de código em poucos arquivos grandes:
    - `frontend/components/connection-dashboard.tsx` ~8.3k linhas
    - `backend/app/services/supabase_store.py` ~8k linhas
    - `backend/app/services/memory_service.py` ~3.6k linhas
    - `backend/app/services/deepseek_service.py` ~2.5k linhas
- O worktree estava sujo durante a análise, principalmente nos arquivos do agente/proatividade; evitar assumir árvore limpa para deploy ou commits automáticos sem conferir `git status`

## Atualização 2026-04-17 4

- Frontend principal foi rebuildado localmente com `npm run build` em `frontend` e publicado no Firebase Hosting target `app`
- URL publicada confirmada no deploy: `https://auracore-82bf2.web.app`
- Backend da proatividade já estava rodando localmente; nesta etapa o publish visível entregue foi o dashboard principal do frontend

## Atualização 2026-04-17 5

- Implementada a rodada de melhoria de memória/agenda/projetos focada em reduzir tokens e aumentar qualidade em consultas operacionais
- Backend:
  - `assistant_context_service` agora prioriza contexto estruturado de agenda/projetos e pode pular retrieval amplo quando a intenção estiver forte
  - `project_memories` ganhou `origin_source` com migração forward-compatible em `sqlite_client`
  - API nova para criação manual:
    - `POST /api/agenda`
    - `POST /api/memories/projects`
  - eventos manuais da agenda usam `message_id` sintético `manual:{uuid}` e entram no mesmo fluxo de conflito/lembrete
- Frontend:
  - aba `Agenda` agora permite criar compromisso manual inline, além de editar/excluir
  - aba `Projetos` agora permite criar projeto manual inline e marca origem manual na UI
- Validação local concluída nesta rodada:
  - `python3 -m py_compile` dos arquivos backend alterados: ok
  - `npm run build` em `frontend`: ok
- Pendência operacional:
  - esta rodada nao reiniciou o backend local nem fez deploy/publicacao nova; se o objetivo for colocar em runtime, ainda precisa sincronizar o runtime/backend e publicar o frontend desejado

## Atualização 2026-04-17 6

- Frontend principal publicado novamente no Firebase Hosting target `app`
  - URL: `https://auracore-82bf2.web.app`
- Backend sincronizado manualmente para o runtime em `/home/server/.local/share/auracore-runtime/repo/backend`
- `auracore-backend.service` reiniciado com sucesso via `systemctl --user`
  - novo `ExecMainPID=362379`
  - `ActiveEnterTimestamp=Fri 2026-04-17 11:31:35 -03`
- Validação pós-restart:
  - `GET /api/memories/status` respondeu `{"detail":"Bearer token ausente."}`
  - `GET /api/whatsapp-agent/proactivity/settings` respondeu `{"detail":"Bearer token ausente."}`
  - isso confirma backend ativo e rotas protegidas carregadas após o restart
