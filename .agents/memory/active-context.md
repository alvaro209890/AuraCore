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
