#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provisiona uma conta local do AuraCore e cria o banco SQLite do usuario.",
    )
    parser.add_argument("--username", required=True, help="Nome de usuario do AuraCore.")
    parser.add_argument(
        "--email",
        help="Email associado. Se omitido, usa <username>@local.auracore.",
    )
    parser.add_argument(
        "--firebase-uid",
        help="UID do Firebase. Se omitido, usa local-<username>.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    sys.path.insert(0, str(backend_dir / ".vendor"))
    sys.path.insert(0, str(backend_dir))
    os.chdir(backend_dir)

    from app.config import Settings
    from app.services.account_registry import AccountRegistry

    settings = Settings()
    registry = AccountRegistry(
        database_root=settings.normalized_database_root,
        registry_path=settings.auth_registry_path,
        message_retention_max_rows=min(
            settings.message_retention_max_rows,
            settings.memory_analysis_max_messages,
        ),
        first_analysis_queue_limit=min(
            settings.memory_first_analysis_max_messages,
            settings.memory_analysis_max_messages,
        ),
    )

    username = args.username.strip()
    email = (args.email or f"{username}@local.auracore").strip().lower()
    firebase_uid = (args.firebase_uid or f"local-{username}").strip()

    account = registry.provision_account(
        firebase_uid=firebase_uid,
        email=email,
        username=username,
    )

    print(f"username={account.username}")
    print(f"firebase_uid={account.firebase_uid}")
    print(f"app_user_id={account.app_user_id}")
    print(f"user_root_path={account.user_root_path}")
    print(f"db_path={account.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
