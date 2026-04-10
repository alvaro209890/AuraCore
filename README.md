# AuraCore

AuraCore roda agora com esta topologia:

- `frontend`: Next.js exportado estaticamente e publicado no Firebase Hosting.
- `backend`: FastAPI rodando neste PC.
- `whatsapp-gateway`: Node.js + Baileys rodando neste PC.
- `cloudflared`: publica a API local em `https://api.cursar.space`.
- `banco local`: SQLite em `/media/acer/dados/Banco_de_dados/AuraCore_DB/auracore.sqlite3`.

## Banco local

- Diretório esperado: `/media/acer/dados/Banco_de_dados/AuraCore_DB`
- Arquivo principal: `/media/acer/dados/Banco_de_dados/AuraCore_DB/auracore.sqlite3`
- O backend inicializa automaticamente o schema SQLite no primeiro boot.
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

Instalação rootless neste PC:

```bash
bash /home/acer/Downloads/AuraCore/scripts/install-user-services.sh
systemctl --user restart auracore-backend.service auracore-whatsapp-gateway.service auracore-cloudflared.service
```

Arquivos relevantes:

- Serviços de usuário: [`deploy/systemd-user`](/home/acer/Downloads/AuraCore/deploy/systemd-user)
- Serviços de sistema: [`deploy/systemd`](/home/acer/Downloads/AuraCore/deploy/systemd)
- Configuração do túnel: [`deploy/cloudflared/config.yml`](/home/acer/Downloads/AuraCore/deploy/cloudflared/config.yml)

Estado atual validado em 10 de abril de 2026:

- API pública: `https://api.cursar.space/health`
- Frontend publicado: `https://auracore-82bf2.web.app`
