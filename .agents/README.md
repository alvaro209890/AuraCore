# `.agents`

Esta pasta existe para reduzir perda de contexto entre agentes de IA que trabalham no AuraCore.

## Leitura obrigatória

Antes de mexer no projeto, o agente deve ler:

- `../AGENTS.md`
- `memory/project-memory.md`
- `memory/active-context.md`

## Escrita obrigatória

Depois de mudanças importantes, o agente deve atualizar:

- `memory/project-memory.md` para fatos estáveis e duráveis do projeto
- `memory/active-context.md` para contexto operacional atual, decisões recentes e pendências

## O que guardar aqui

- Estrutura real do projeto
- Caminhos críticos
- Serviços e deploy
- Convenções internas
- Fluxos operacionais importantes
- Bugs recentes, correções e limitações conhecidas

## O que não guardar aqui

- Segredos
- Tokens
- Dumps longos de terminal
- Texto redundante ou genérico
