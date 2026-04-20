# Active Context

## Estado operacional recente

- O modo CLI do WhatsApp foi removido do backend e das UIs públicas
- O segundo site (`agent-frontend`) continua sendo o painel do QR do agente global, mas sem seção de admins/CLI
- O agente global agora responde apenas ao owner mapeado por `observer_owner_phone`
- Chat e proatividade usam somente o canal global `agent`; o `observer` ficou restrito à identificação da conta e do owner

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

## Atualização 2026-04-17 7

- Nova rodada de melhoria da proatividade implementada no backend sem mexer no frontend
- Ajustes aplicados:
  - `assistant_context_service` agora consegue recuperar e formatar `important_messages` no contexto ativo quando o plano do DeepSeek pedir isso
  - `deepseek_service` foi estendido para:
    - `important_message_queries` no search plan
    - ações concretas para `project_nudge`
    - campos de importância no `extract_agent_memory`
    - alternativas sugeridas na resolução de conflito de agenda
  - `whatsapp_agent_service` agora pode salvar `important_messages` já no fluxo de aprendizado da mensagem inbound
  - `proactive_assistant_service` agora:
    - gera `suggested_actions` para nudges de projeto
    - aplica `moment_state` heurístico (`high_focus`, `available`, `busy`, `low_energy`) antes de enviar
    - registra esse contexto no scoring/log do envio
  - `agenda_guardian_service` agora sugere slots livres quando detecta conflito
- Validação local desta rodada:
  - `python3 -m py_compile` dos serviços alterados: ok
  - backend sincronizado para o runtime local
  - `auracore-backend.service` reiniciado com sucesso
    - `ExecMainPID=367297`
    - `ActiveEnterTimestamp=Fri 2026-04-17 11:44:27 -03`
  - `GET /api/whatsapp-agent/proactivity/settings` respondeu `{"detail":"Bearer token ausente."}`
  - `GET /api/memories/status` respondeu `{"detail":"Bearer token ausente."}`
- Limitação atual:
  - nao houve smoke test funcional ponta a ponta com mensagens reais do WhatsApp nesta rodada; a validacao foi estrutural/operacional

## Atualização 2026-04-17 8

- Auditoria do frontend modular confirmou que a refatoração das abas estava ativa no app, mas ainda não estava segura para manter no repositório porque:
  - `frontend/components/dashboard/tabs/` existia localmente e era usado pelo app atual
  - essa pasta ainda não estava versionada no Git
  - `frontend/old_dashboard.tsx` e scripts `frontend/fix_*.py` eram artefatos locais de refatoração
- Ação aplicada:
  - abas modulares preparadas para entrar no repositório principal
  - artefatos locais de scratch passaram a ser ignorados por `.gitignore`
- Validação local desta rodada:
  - `npm run build` em `frontend`: ok
  - `npx tsc --noEmit` em `frontend` após o build: ok
  - frontend publicado novamente no Firebase Hosting:
    - `https://auracore-82bf2.web.app`

## Atualização 2026-04-17 9

- Refatoração visual forte entregue nas abas `Agenda`, `Automação` e `Proatividade` do frontend principal
- Ajustes aplicados:
  - `AgendaTab` ganhou formulário de criação/edição mais moderno, cards mais legíveis e melhor hierarquia para conflitos, origem e lembretes
  - `AutomationTab` deixou de ser só leitura parcial e passou a expor configuração operacional real do loop com toggles, campos numéricos e histórico reorganizado
  - `ProactivityTab` foi reestruturada com configuração mais clara de janelas, intensidade, categorias, fila ativa e entregas recentes
  - `frontend/app/globals.css` recebeu um conjunto compartilhado de estilos `ops-*` para inputs, selects, toggles e superfícies operacionais dessas abas
- Validação local desta rodada:
  - `npm run build` em `frontend`: ok

## Atualização 2026-04-17 10

- Corrigido bug de roteamento da proatividade no backend
- Causa identificada:
  - `ProactiveAssistantService` resolvia o owner target preferindo `agent_status`/`agent_session`
  - se o agent global estivesse conectado em outro número, a proatividade podia mandar o nudge para esse owner errado em vez do owner do `observer` da conta atual
- Ajuste aplicado:
  - proatividade agora resolve primeiro o owner do `observer`
  - usa o phone configurado do Álvaro como fallback seguro
  - fallback vindo do `agent` só é aceito se bater com o owner esperado; caso contrário gera warning e é ignorado
- Hardening adicional:
  - `agenda_guardian_service` recebeu a mesma proteção de owner target para lembretes e conflitos não repetirem o mesmo bug de roteamento
- Validação local desta rodada:
  - `python3 -m py_compile backend/app/services/proactive_assistant_service.py backend/app/services/agenda_guardian_service.py`: ok
  - backend sincronizado para o runtime local
  - `auracore-backend.service` reiniciado com sucesso
    - `ExecMainPID=423461`
    - `ActiveEnterTimestamp=Fri 2026-04-17 14:25:42 -03`

## Atualização 2026-04-17 11

- Endurecida a criação de projetos vinda da análise do observador
- Ajustes aplicados:
  - `deepseek_service` agora exige menos projetos vagos e mais detalhe concreto em `summary`, `what_is_being_built`, `built_for`, `next_steps` e `evidence`
  - `memory_service` passou a refinar candidatos de projeto com base nas mensagens-fonte, puxando evidências/snippets reais, próximos passos acionáveis e recompondo resumos fracos
  - projetos sem detalhe mínimo útil agora são descartados antes de persistir ou estabilizar o resultado da análise

## Atualização 2026-04-20

- Removido o arquivo `backend/app/services/whatsapp_cli_service.py` e toda a interceptação de CLI no `WhatsAppAgentService`
- `internal_agent` já roteava por `observer_owner_phone`; agora o `WhatsAppAgentService` também só aceita o owner do `observer` da conta e não depende mais de `whatsapp_known_contacts`/admins
- `ProactiveAssistantService` e `agenda_guardian_service` passaram a resolver o alvo apenas pelo `observer` e enviar somente via `agent_gateway`
- APIs `/api/global-agent/admin-contacts` e `/api/whatsapp-agent/admin-contacts` foram removidas; `workspace` do agente não expõe mais `terminal_session`
- As respostas de chat do WhatsApp deixaram de usar DeepSeek e agora passam por `GroqChatService` com `WHATSAPP_AGENT_GROQ_MODEL` default `llama-3.3-70b-versatile`
- Validação local concluída:
  - `python3 -m py_compile` dos módulos backend alterados: ok
  - `npm run build` em `agent-frontend`: ok
  - `npm run build` em `frontend`: ok
- Validação local desta rodada:
  - `python3 -m py_compile backend/app/services/memory_service.py backend/app/services/deepseek_service.py`: ok
  - backend sincronizado para o runtime local
  - `auracore-backend.service` em execução após restart
    - `ExecMainPID=425502`
    - `ActiveEnterTimestamp=Fri 2026-04-17 14:30:42 -03`

## Atualização 2026-04-17 12

- Consolidação final da rodada para publicação
- Validação repetida antes do commit:
  - `python3 -m py_compile` dos serviços alterados de backend: ok
  - `npm run build` em `frontend`: ok
- Runtime local alinhado novamente com os serviços alterados:
  - `proactive_assistant_service.py`
  - `agenda_guardian_service.py`
  - `memory_service.py`
  - `deepseek_service.py`
- Backend validado em execução:
  - `auracore-backend.service` reiniciado com sucesso e ficou `active/running`
    - `ExecMainPID=427135`
    - `ActiveEnterTimestamp=Fri 2026-04-17 14:33:54 -03`
  - journal recente mostrou rotas reais do dashboard servindo `200 OK`
  - checagens locais sem token em `/api/memories/status` e `/api/whatsapp-agent/proactivity/settings` responderam `Bearer token ausente`, confirmando backend ativo e rotas protegidas carregadas

## Atualização 2026-04-17 13

- Refatoração visual profunda aplicada nas abas `Proatividade` e `Automação` do frontend principal
- Ajustes aplicados:
  - `ProactivityTab` foi reorganizada em painéis de presença, silêncio, cadência, digests e categorias
  - `AutomationTab` foi reorganizada em painéis de estados automáticos, gatilhos, janela de leitura e budget
  - `frontend/app/globals.css` recebeu shells escuros para `input/select/time/number`, botões `ops-hero-button`, pills segmentadas e painéis `ops-control-panel`
  - o problema visual de campos simples/brancos ficou tratado no kit compartilhado, não só pontualmente em cada aba
- Validação local desta rodada:
  - `npm run build` em `frontend`: ok
- Deploy:
  - Firebase Hosting target `app` publicado novamente
  - URL: `https://auracore-82bf2.web.app`

## Atualização 2026-04-17 14

- Correções aplicadas após a auditoria funcional de `Automação`, `Proatividade` e `Agenda`
- Mudanças principais:
  - `Automação`: `auto_sync_enabled` agora governa o loop automático de ingest/sync; jobs incrementais automáticos passaram a usar `default_detail_mode`, `default_target_message_count` e `default_lookback_hours`; `auto_refine_enabled` pode enfileirar `refine_saved` quando o backlog acabar
  - `Automação` e `Proatividade`: validações numéricas do frontend foram alinhadas aos contratos do backend
  - `Proatividade`: a UI deixou de expor `Agenda` como categoria proativa; o cooldown global mínimo agora consulta apenas entregas `sent`
  - `Agenda`: criação/edição manual foi refatorada para shells `ops-*`, status em pills e presets de lembrete, removendo campos visuais crus/brancos
- Validação local desta rodada:
  - `python3 -m py_compile` em `automation_service.py`, `proactive_assistant_service.py` e `supabase_store.py`: ok
  - `npm run build` em `frontend`: ok

## Atualização 2026-04-17 15

- Runtime local sincronizado com:
  - `automation_service.py`
  - `proactive_assistant_service.py`
  - `supabase_store.py`
  - `memory_service.py`
- Correção extra aplicada no backend: `memory_service.get_analysis_preview()` estava chamando `_build_analysis_prompt_context_for_intent` com variável `intent` inexistente; passou a usar `resolved_intent`
- Backend:
  - `auracore-backend.service` reiniciado com sucesso e ficou `active/running`
  - após o restart, o serviço voltou processando um job automático já reenfileirado no warm start
  - `GET /api/memories/status` local respondeu `401 Bearer token ausente`, confirmando servidor ativo e rotas protegidas carregadas
- Frontend:
  - `firebase deploy --only hosting:app`: ok
  - URL publicada: `https://auracore-82bf2.web.app`
