# WhatsApp Flow — Observer + Agent

## Dois Canais WhatsApp

### Observer (`instance: observer`)
- **Funcao:** Captura mensagens do WhatsApp e envia para o backend
- **Biblioteca:** Baileys (`@whiskeysockets/baileys`)
- **Gateway:** Express em `127.0.0.1:10001`
- **QR Code:** Vinculacao via `POST /internal/observer/connect`

### Agent (`instance: agent`)
- **Funcao:** Responde automaticamente contatos via WhatsApp
- **Sessoes:** Uma sessao ativa por thread/contato
- **Idle timeout:** 10 minutos sem atividade → sessao encerrada

## Fluxo de Ingestao (Observer)

```
1. Usuario escaneia QR → observer conecta
2. Gateway dispara syncFullHistory
3. Mensagens sao enviadas para:
   POST /api/internal/observer/messages/ingest
4. Backend salva no SQLite:
   - Apenas chats diretos com texto
   - Ignora grupos, status, midias sem texto, duplicatas
5. wa_sync_run e fechado quando sync assenta
```

## Sessoes e Credenciais

- Credenciais QR persistidas em SQLite (`wa_sessions` + `wa_session_keys`)
- Observer reconecta automaticamente apos reboot se sessao valida
- E normal aparecer QR do `agent` mesmo com `observer` conectado (canais independentes)

## WhatsApp Gateway API (Interna)

Endpoints protegidos por `x-internal-api-token`:

| Endpoint | Funcao |
|----------|--------|
| `GET /internal/observer/status` | Status do observer |
| `POST /internal/observer/connect` | Conectar observer (gera QR) |
| `POST /internal/observer/reset` | Reset observer |
| `POST /internal/observer/messages/refresh` | Forcar refresh historico |
| `POST /internal/observer/send` | Enviar mensagem como observer |
| `GET /internal/agent/status` | Status do agent global |
| `POST /internal/agent/connect` | Conectar agent |
| `POST /internal/agent/reset` | Reset agent |
| `POST /internal/agent/send` | Enviar mensagem como agent |

## Fluxo do Agente WhatsApp

```
1. Mensagem inbound chega no observer → backend ingere
2. whatsapp_agent_service detecta contato/thread
3. Se auto_reply_enabled e sessao ativa:
   a. Carrega contexto (memoria do contato + projetos ativos)
   b. Chama Groq/DeepSeek para gerar resposta
   c. Envia via gateway (`POST /internal/agent/send`)
4. Sessao encerra apos idle timeout (10 min)
```
