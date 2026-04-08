# AuraCore

AuraCore e o segundo cerebro digital centrado em dois numeros de WhatsApp:

- `Numero A (Observador)`: lido pelo sistema para aprender contexto, rotina e relacionamentos.
- `Numero B (Assistente)`: respondera ao usuario nas fases seguintes.

## Estrutura

- [`backend`](/home/acer/Downloads/AuraCore/backend): FastAPI para Evolution API, webhook e persistencia no Supabase.
- [`frontend`](/home/acer/Downloads/AuraCore/frontend): dashboard Next.js para conectar o WhatsApp observador.
- [`supabase/migrations`](/home/acer/Downloads/AuraCore/supabase/migrations): schema inicial com `pgvector`.

## Fase 1 implementada

- Criacao e configuracao da instancia observadora na Evolution API.
- Geracao de QR Code e consulta de status.
- Webhook por evento para `MESSAGES_UPSERT` e `CONNECTION_UPDATE`.
- Persistencia de mensagens textuais diretas na tabela `mensagens`.
- Tabela `persona` criada para a proxima fase.

## Como rodar

### Backend

1. Copie [`backend/.env.example`](/home/acer/Downloads/AuraCore/backend/.env.example) para `.env`.
2. Instale dependencias com `pip install -r requirements.txt`.
3. Inicie com `uvicorn app.main:app --reload --port 8000`.

### Frontend

1. Copie [`frontend/.env.example`](/home/acer/Downloads/AuraCore/frontend/.env.example) para `.env.local`.
2. Instale dependencias com `npm install`.
3. Inicie com `npm run dev`.

## Deploy

No Render, use `/backend` como root directory do servico Python e configure o comando:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

