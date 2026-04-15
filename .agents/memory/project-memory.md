# Project Memory

## Identidade do projeto

- Repositório principal: `AuraCore`
- Branch principal usada em produção: `main`
- Backend em produção local roda a partir do runtime em `/home/server/.local/share/auracore-runtime/repo/backend`
- Repositório principal fica em `/media/server/HD Backup/Servidores_NAO_MEXA/AuraCore`

## WhatsApp Agent / CLI

- Existe um modo agente/CLI do WhatsApp para o Álvaro
- O Álvaro (`6684396232`) deve ser tratado como admin no fluxo do agente
- O backend já suporta sessão terminal persistida, contexto CLI, progresso intermediário e mensagem final de conclusão
- Quando mudanças do backend são feitas, normalmente é preciso sincronizar runtime e repositório principal antes de commitar

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
