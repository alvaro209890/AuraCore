# AuraCore

AuraCore roda agora com esta topologia:

- `frontend`: Next.js exportado estaticamente e publicado no Firebase Hosting.
- `backend`: FastAPI rodando neste PC.
- `whatsapp-gateway`: Node.js + Baileys rodando neste PC.
- `cloudflared`: publica a API local em `https://api.cursar.space`.
- `banco local`: SQLite em `/media/acer/dados/Banco_de_dados/AuraCore_DB/auracore.sqlite3`.
- `auto-update`: timer local via `systemd --user` que aplica `git pull` da `main` e reinicia os servicos afetados.

Documentacao operacional detalhada:

- [`docs/local-backend-runtime.md`](/home/acer/Downloads/AuraCore/docs/local-backend-runtime.md)

## Banco local

- Diretório esperado: `/media/acer/dados/Banco_de_dados/AuraCore_DB`
- Arquivo principal: `/media/acer/dados/Banco_de_dados/AuraCore_DB/auracore.sqlite3`
- O backend inicializa automaticamente o schema SQLite no primeiro boot.
- O backend tambem aplica migracoes locais nao destrutivas no startup quando faltam colunas legadas do SQLite.
- A migracao atual inclui compatibilidade para `mensagens.embedding`, alem das colunas de analise e retencao usadas pelas telas novas.
- A sessão do WhatsApp também fica nesse banco via `wa_sessions` e `wa_session_keys`.

## Variáveis principais

### Backend

Use [`backend/.env.example`](/home/acer/Downloads/AuraCore/backend/.env.example) como base.

Campos obrigatórios no runtime:

- `AURACORE_DB_PATH`
- `WHATSAPP_GATEWAY_URL`
- `INTERNAL_API_TOKEN`

Campos opcionais, mas necessários para análise e chat:

- `DEEPSEEK_API_KEY`
- `GROQ_API_KEY`

### Gateway

Use [`whatsapp-gateway/.env.example`](/home/acer/Downloads/AuraCore/whatsapp-gateway/.env.example) como base.

Campos obrigatórios:

- `AURACORE_API_BASE_URL`
- `INTERNAL_API_TOKEN`

### Frontend

Use [`frontend/.env.example`](/home/acer/Downloads/AuraCore/frontend/.env.example) para dev local.

Para o build publicado no Firebase, o valor esperado é:

- `NEXT_PUBLIC_API_BASE_URL=https://api.cursar.space`

## Desenvolvimento local

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Gateway

```bash
cd whatsapp-gateway
npm install
npm run build
npm run start
```

### Frontend

```bash
cd frontend
npm install
npm run build
```

## Produção local neste PC

- `auracore-backend.service`: sobe o FastAPI em `127.0.0.1:8000`
- `auracore-whatsapp-gateway.service`: sobe o gateway em `127.0.0.1:10001`
- `auracore-cloudflared.service`: publica `api.cursar.space -> http://127.0.0.1:8000`
- `auracore-auto-update.timer`: verifica a `main` no GitHub a cada 2 minutos
- `auracore-auto-update.service`: executa `git fetch`, `git pull --ff-only` e reinicia backend/gateway/cloudflared quando necessario

Instalação rootless neste PC:

```bash
bash /home/acer/Downloads/AuraCore/scripts/install-user-services.sh
systemctl --user restart auracore-backend.service auracore-whatsapp-gateway.service auracore-cloudflared.service
```

Persistencia no boot deste PC:

- O usuario `acer` precisa estar com `linger` habilitado.
- Neste PC isso ja foi ativado com `loginctl enable-linger acer`.
- Com isso, backend, gateway, cloudflared e o timer de auto-update sobem mesmo sem login grafico manual.

Regras do auto-update:

- Monitora `origin/main`.
- So aplica atualizacao automatica quando a arvore Git local estiver limpa.
- Se houver alteracoes rastreadas locais, o ciclo e pulado para nao sobrescrever trabalho.
- Quando `whatsapp-gateway/package.json` ou `package-lock.json` mudam, o timer executa `npm install` antes de reiniciar o gateway.

## Observador WhatsApp

- O processo do gateway sobe dois canais: `observer` e `agent`.
- O `observer` e o canal que puxa historico e mensagens novas para o banco local.
- Quando o `observer` e religado por QR, o backend guarda ate 120 mensagens operacionais recentes para a primeira analise e enfileira essa leitura automaticamente quando a sincronizacao assenta.
- Depois da primeira analise, o backend continua recebendo mensagens novas em tempo real e abre lotes incrementais automaticos quando a fila atinge o limiar configurado.
- E normal ainda aparecer QR apos o `observer` conectar, porque o canal `agent` pode continuar aguardando vinculacao separada.
- As credenciais do QR ficam persistidas no SQLite local via `wa_sessions` e `wa_session_keys`, entao o `observer` reconecta sozinho apos reboot quando a sessao continua valida no WhatsApp.

Arquivos relevantes:

- Serviços de usuário: [`deploy/systemd-user`](/home/acer/Downloads/AuraCore/deploy/systemd-user)
- Serviços de sistema: [`deploy/systemd`](/home/acer/Downloads/AuraCore/deploy/systemd)
- Configuração do túnel: [`deploy/cloudflared/config.yml`](/home/acer/Downloads/AuraCore/deploy/cloudflared/config.yml)
- Script de auto-update: [`scripts/auto-update.sh`](/home/acer/Downloads/AuraCore/scripts/auto-update.sh)
- Schema SQLite local: [`backend/app/services/sqlite_schema.sql`](/home/acer/Downloads/AuraCore/backend/app/services/sqlite_schema.sql)

Estado atual validado em 10 de abril de 2026:

- API pública: `https://api.cursar.space/health`
- Frontend publicado: `https://auracore-82bf2.web.app`
