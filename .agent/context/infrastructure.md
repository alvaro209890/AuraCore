# Infrastructure — Deploy, Tunel, Auto-Update

## Deploy Local (Producao no PC)

### Systemd User Services

Todos rodam como `systemd --user` do usuario `acer`:

| Service | Funcao |
|---------|--------|
| `auracore-backend.service` | FastAPI em 127.0.0.1:8000 |
| `auracore-whatsapp-gateway.service` | Baileys/Express em 127.0.0.1:10001 |
| `auracore-cloudflared.service` | Tunnel para api.cursar.space |
| `auracore-auto-update.timer` | Timer a cada 2 min |
| `auracore-auto-update.service` | Git pull + restart |

**Boot sem login:** `loginctl enable-linger acer`

### Instalacao

```bash
bash scripts/install-user-services.sh
```

Esse script:
- Cria diretorios do SQLite
- Instala units em `~/.config/systemd/user`
- Habilita e sobe todos os servicos

## Cloudflare Tunnel

**Como funciona:**

```
Browser → api.cursar.space (HTTPS via Cloudflare Edge)
  → Tunnel persistente (cloudflared)
    → http://127.0.0.1:8000 (backend FastAPI)
```

**Config:** `deploy/cloudflared/config.yml`
- Tunnel ID: `e759f152-1746-4a22-9ad8-f2131a36b84c`
- Credenciais: `~/.cloudflared/e759f152-...json`
- Ingress: `api.cursar.space → http://127.0.0.1:8000`

**Frontend → Backend:**
```
auracore-82bf2.web.app (Firebase static)
  → fetch("https://api.cursar.space/api/...")
    → Cloudflare → cloudflared → 127.0.0.1:8000
```

## Auto-Update

```
Timer (2 min)
  → auto-update.sh:
    1. git fetch origin
    2. Se working tree limpa: git pull --ff-only
    3. Se package.json mudou: npm install no gateway
    4. Reinstala systemd units
    5. Reinicia backend/gateway/cloudflared
```

**Seguranca:** Se arvore Git local estiver suja, pula a atualizacao para nao sobrescrever trabalho em andamento.

## Docker / Render

`Dockerfile` empacota backend + gateway em uma imagem unica:
- Python 3 (venv) + Node 20
- Render deploy via `render.yaml`
- Health check: `/health`
- Render keepalive a cada 600s (plano free)

## Frontend Deploy

**Firebase Hosting** com 2 targets:
- `app` → `frontend/out/` (dashboard usuario)
- `agent` → `agent-frontend/out/` (dashboard agente)

Build: `next build` (static export)

## Variaveis de Ambiente

### Backend (obrigatorias)
| Variavel | Descricao |
|----------|-----------|
| `AURACORE_DB_PATH` | Caminho do SQLite |
| `WHATSAPP_GATEWAY_URL` | URL do gateway interno |
| `INTERNAL_API_TOKEN` | Token de autenticacao interno |

### Backend (opcionais mas necessarias)
| Variavel | Default |
|----------|---------|
| `DEEPSEEK_API_KEY` | — |
| `GROQ_API_KEY` | — |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `GROQ_MODEL` | `llama-3.1-8b-instant` |

### Frontend
| Variavel | Producao |
|----------|----------|
| `NEXT_PUBLIC_API_BASE_URL` | `https://api.cursar.space` |

### Gateway
| Variavel | Descricao |
|----------|-----------|
| `AURACORE_API_BASE_URL` | URL do backend |
| `INTERNAL_API_TOKEN` | Mesmo token do backend |
