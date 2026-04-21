#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_runtime_modules() -> None:
    backend_path = _repo_root() / "backend"
    sys.path.insert(0, str(backend_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona e faz replay heurístico de casos reais do WhatsApp CLI.")
    parser.add_argument("--db", required=True, help="Caminho do sqlite real do usuário.")
    parser.add_argument("--thread-id", default="b91f3512-7280-4f48-9014-4167b4bdc8ec")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    _load_runtime_modules()
    os.environ.setdefault("WHATSAPP_GATEWAY_URL", "http://127.0.0.1")
    os.environ.setdefault("INTERNAL_API_TOKEN", "replay-cli")
    from app.config import Settings
    from app.services.deepseek_service import DeepSeekService
    from app.services.banco_de_dados_local_store import BancoDeDadosLocalStore
    from app.services.whatsapp_cli_service import WhatsAppCliService

    settings = Settings()
    store = BancoDeDadosLocalStore(
        database_path=args.db,
        default_user_id=settings.default_user_id,
        message_retention_max_rows=20,
        first_analysis_queue_limit=20,
    )
    cli = WhatsAppCliService(
        settings=settings,
        store=store,
        deepseek_service=DeepSeekService(settings),
    )

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT content, metadata, created_at
        FROM whatsapp_agent_messages
        WHERE thread_id = ? AND direction = 'inbound'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (args.thread_id, args.limit),
    ).fetchall()

    for row in reversed(rows):
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        if metadata.get("interaction_mode") != "cli":
            continue
        content = row["content"]
        cwd = str(metadata.get("cli_cwd") or settings.normalized_whatsapp_cli_root)
        plan = cli._try_build_heuristic_plan(message_text=content, cwd=cwd)
        print("===")
        print(row["created_at"])
        print(content)
        if plan is None:
            print("heuristic_plan=None")
            continue
        print(plan.summary)
        for action in plan.actions:
            print(f"- {action.tool}: {action.command or action.path or action.explanation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
