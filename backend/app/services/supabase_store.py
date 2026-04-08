from __future__ import annotations

from typing import Sequence
from uuid import UUID

from supabase import Client, create_client

from app.services.message_parser import NormalizedMessage


class SupabaseStore:
    def __init__(self, supabase_url: str, supabase_key: str, default_user_id: UUID) -> None:
        self.client: Client = create_client(supabase_url, supabase_key)
        self.default_user_id = default_user_id

    def save_messages(self, messages: Sequence[NormalizedMessage]) -> int:
        if not messages:
            return 0

        records = [
            {
                "id": message.id,
                "user_id": str(message.user_id),
                "contact_name": message.contact_name,
                "message_text": message.message_text,
                "timestamp": message.timestamp.isoformat(),
                "embedding": None,
            }
            for message in messages
        ]

        self.client.table("mensagens").upsert(records, on_conflict="id").execute()
        return len(records)

