# AuraCore — Contexto para Agentes de IA

> Leia este arquivo primeiro para entender o projeto. Os arquivos no subdiretorio `context/` detalham cada servico.

## O que e o Projeto

AuraCore e um assistente pessoal com integracao ao WhatsApp que:
1. Observa conversas do WhatsApp (canal `observer`)
2. Analisa memorias automaticamente via DeepSeek/Groq (fatos, projetos, relacionamentos)
3. Oferece chat com contexto de memoria
4. Mantem agenda com lembretes
5. Responde automaticamente via WhatsApp (canal `agent`)

## Topologia de Producao Local

```
Frontend (Firebase)        Cloudflare Tunnel        Backend Local
auracore-82bf2.web.app --> api.cursar.space -----> 127.0.0.1:8000 (FastAPI)
                                                   |
                                                   v
                                            SQLite local DB
                                                   ^
                                                   |
WhatsApp Gateway (127.0.0.1:10001) ----------------+
  observer + agent (Baileys)
```

## Servicos

| Servico | Stack | Dir | Porta | Deploy |
|---------|-------|-----|-------|--------|
| Backend | FastAPI + Python + SQLite | `backend/` | 8000 | systemd user + Docker/Render |
| WhatsApp Gateway | Node.js + Baileys + Express | `whatsapp-gateway/` | 10001 | systemd user + Docker |
| Frontend (usuario) | Next.js 15 + React 19 + Firebase | `frontend/` | 3000 | Firebase Hosting (static) |
| Agent Frontend | Next.js 15 + React 19 + Firebase | `agent-frontend/` | 3001 | Firebase Hosting (static) |
| Cloudflare Tunnel | cloudflared | — | — | systemd user |

## Backend Local — Como Rodo

1. **systemd user service** carrega `backend/.env`
2. Chama `scripts/run-backend-prod.sh` que:
   - Ativa `.venv` do backend (fallback: `python3`)
   - Injeta `backend/.vendor` no `PYTHONPATH`
   - Executa: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
3. Services: `deploy/systemd-user/auracore-backend.service`

**Dev local manual:**
```bash
cd backend && . .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Cloudflare Tunnel — Como Funciona

- **Config:** `deploy/cloudflared/config.yml` + `deploy/cloudflared/auracore-config.yml`
- **Tunnel ID:** `e759f152-1746-4a22-9ad8-f2131a36b84c`
- **Credenciais:** `~/.cloudflared/e759f152-1746-4a22-9ad8-f2131a36b84c.json`
- **Ingress:** `api.cursar.space` → `http://127.0.0.1:8000`
- **Service:** `deploy/systemd-user/auracore-cloudflared.service`

O tunel escuta HTTPS em `api.cursar.space` e encaminha para o backend local. O frontend (hospedado no Firebase) chama a API via `https://api.cursar.space`.

**Fluxo completo:**
```
Browser → auracore-82bf2.web.app (Firebase static)
  → fetch("https://api.cursar.space/api/...")
    → Cloudflare Edge
      → cloudflared tunnel (persistente)
        → http://127.0.0.1:8000 (FastAPI local)
```

## Auto-Update

Timer systemd verifica `origin/main` a cada 2 min. Aplica `git pull --ff-only` e reinicia servicos. Pula se arvore Git estiver suja.

## Banco de Dados

- **SQLite local:** `/home/acer/Documentos/Bando_de_dados/Aura_Core/sqlite/auracore.sqlite3`
- **Schema base:** `backend/app/services/sqlite_schema.sql`
- **Migracoes:** aplicadas automaticamente no startup (non-destructive)
- **Sessoes WhatsApp:** persistidas em `wa_sessions` + `wa_session_keys`

## Arquivos de Contexto Detalhado

| Arquivo | Conteudo |
|---------|----------|
| `context/architecture.md` | Estrutura do backend, routers, servicos, schemas |
| `context/whatsapp-flow.md` | Fluxo observer/agent, ingestao, sessoes QR |
| `context/memory-pipeline.md` | Pipeline de analise de memoria, automacao, tokens |
| `context/infrastructure.md` | Deploy, systemd, tunel, auto-update, variaveis |

## Regras ao Modificar Codigo

- Backend usa **pydantic-settings** para configuracao via `.env`
- Frontend e **static export** (`next build` → `out/`) — nao ha SSR
- WhatsApp gateway usa **Baileys** — nao modifique a logica de sessao sem testar QR
- Migracoes SQLite sao **non-destructive** — nunca remova colunas existentes
- O tunel cloudflared depende do backend estar em `127.0.0.1:8000`
- Variaveis obrigatorias: `AURACORE_DB_PATH`, `WHATSAPP_GATEWAY_URL`, `INTERNAL_API_TOKEN`
