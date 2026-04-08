# AuraCore

AuraCore e o segundo cerebro digital centrado em dois numeros de WhatsApp:

- `Numero A (Observador)`: lido pelo sistema para aprender contexto, rotina e relacionamentos.
- `Numero B (Assistente)`: respondera ao usuario nas fases seguintes.

## Estrutura

- [`backend`](/home/acer/Downloads/AuraCore/backend): FastAPI publico para status do observador, analise DeepSeek e persistencia no Supabase.
- [`frontend`](/home/acer/Downloads/AuraCore/frontend): dashboard Next.js para conectar o WhatsApp e disparar analises manuais.
- [`whatsapp-gateway`](/home/acer/Downloads/AuraCore/whatsapp-gateway): microservico Node.js com Baileys, QR Code e ingestao de mensagens.
- [`supabase/migrations`](/home/acer/Downloads/AuraCore/supabase/migrations): schema inicial e upgrade para snapshots de memoria.

## O que esta implementado

- Conexao do WhatsApp observador via Baileys com sessao persistida no Supabase.
- QR Code, status e reconexao pelo `whatsapp-gateway`.
- Ingestao de chats diretos de entrada e saida para a tabela `mensagens`.
- Analise manual por janela de horas com `deepseek-chat`.
- Atualizacao de `persona.life_summary` e gravacao de `memory_snapshots`.
- Dashboard unico com conexao, resumo atual e historico de analises.

## Como rodar

### Backend

1. Copie [`backend/.env.example`](/home/acer/Downloads/AuraCore/backend/.env.example) para `.env`.
2. Instale dependencias com `pip install -r requirements.txt`.
3. Inicie com `uvicorn app.main:app --reload --port 8000`.

### WhatsApp Gateway

1. Copie [`whatsapp-gateway/.env.example`](/home/acer/Downloads/AuraCore/whatsapp-gateway/.env.example) para `.env`.
2. Instale dependencias com `npm install`.
3. Inicie com `npm run dev`.

### Frontend

1. Copie [`frontend/.env.example`](/home/acer/Downloads/AuraCore/frontend/.env.example) para `.env.local`.
2. Instale dependencias com `npm install`.
3. Inicie com `npm run dev`.

### Supabase

1. Aplique [`20260408190000_initial_schema.sql`](/home/acer/Downloads/AuraCore/supabase/migrations/20260408190000_initial_schema.sql).
2. Em seguida aplique [`20260408203000_memory_analysis_schema.sql`](/home/acer/Downloads/AuraCore/supabase/migrations/20260408203000_memory_analysis_schema.sql).
3. Por fim aplique [`20260408230000_whatsapp_session_storage.sql`](/home/acer/Downloads/AuraCore/supabase/migrations/20260408230000_whatsapp_session_storage.sql).

## Deploy

O deploy em producao pode rodar em um unico servico da Render usando Docker:

- o FastAPI fica publico na porta do servico;
- o gateway Baileys roda no mesmo container em `127.0.0.1:10001`;
- a sessao do WhatsApp fica salva no Supabase, sem precisar de disco persistente.

O arquivo [`render.yaml`](/home/acer/Downloads/AuraCore/render.yaml) ja descreve esse modo single-service.

Se voce optar por Render free, pode manter o servico mais ativo com ping externo em `/health`, mas a Render ainda pode reiniciar o servico. Como a sessao do WhatsApp fica no Supabase, o QR normalmente nao precisa ser lido de novo apos esses restarts.
