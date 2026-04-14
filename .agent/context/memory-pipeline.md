# Memory Pipeline — Analise e Automacao

## Pipeline de Analise de Memoria

O backend usa DeepSeek para analisar conversas do WhatsApp e extrair:
- **Persona:** Resumo de vida, rotinas, preferencias, perguntas abertas
- **Memory Snapshots:** Analise temporal de um periodo de conversas
- **Project Memories:** Projetos ativos inferidos (o que esta sendo construido, proximos passos)
- **Person Memories:** Fatos sobre contatos/pessoas

## Tipos de Analise

| Tipo | Trigger | Max Mensagens |
|------|---------|---------------|
| First Analysis | Pos-primeiro sync do observer | 120 |
| Incremental | Fila atinge 20 mensagens novas | 20 em batch |
| Manual/Refine | Usuario solicita via frontend | 160 |

## Chunking da First Analysis

Quando ha muitas mensagens (>60), a primeira analise e dividida em chunks:
- `CHUNK_TRIGGER_MESSAGES = 60` — ativa chunking
- `CHUNK_SIZE = 36` — mensagens por chunk
- `CHUNK_CHAR_BUDGET = 6500` — chars por chunk
- `SYNTHESIS_GROUP_SIZE = 2` — chunks agrupados na sintese final

## Estimativa de Tokens e Custos

O sistema calcula antes de cada analise:
- Tokens de input/output estimados
- Custo em USD (floor e ceiling)
- Capacidade maxima de mensagens pelo modelo
- Budget de chars do contexto

## Automacao

```
wa_sync_run (novo sync)
  → automation_service avalia:
    - min_new_messages_threshold (limiar de novas msgs)
    - stale_hours_threshold (horas sem analise)
    - daily_budget_usd (orcamento diario)
    - max_auto_jobs_per_day (teto de jobs)
  → Se condicoes OK: cria analysis_job
    → memory_job_service executa:
      1. Seleciona mensagens (balanceadas, recentes)
      2. Monta prompt com contexto (persona, projetos, pessoas)
      3. Chama DeepSeek (planner → stack → synthesize)
      4. Salva snapshot, projetos, pessoas no SQLite
      5. Atualiza persona
```

## Estados de Job

`queued` → `running` → `completed` ou `failed`

Progresso tracked via: `progress_percent`, `live_stage`, `live_status_text`

## Retencao de Mensagens

- `MESSAGE_RETENTION_MAX_ROWS = 160` — teto de msgs no banco
- Prune automatico remove msgs mais antigas quando excede
- `observer_history_cutoff_at` marca corte do historico antigo apos primeira analise
