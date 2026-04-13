-- ============================================================
-- AuraCore SQLite forward-compatible migrations
-- These run BEFORE the main schema to add missing columns and
-- tables so that CREATE INDEX IF NOT EXISTS does not fail.
-- Every statement uses IF NOT EXISTS or checks pragmatically.
-- ============================================================

-- 1. Add missing columns to mensagens (group support)
-- SQLite does not support ADD COLUMN IF NOT EXISTS directly,
-- so we wrap each in a no-op-safe pattern.

-- We handle this programmatically in the SQLiteClient migration runner.

-- 2. Create whatsapp_known_groups if missing
CREATE TABLE IF NOT EXISTS whatsapp_known_groups (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  chat_jid TEXT NOT NULL,
  chat_name TEXT NOT NULL DEFAULT '',
  enabled_for_analysis INTEGER NOT NULL DEFAULT 0,
  last_seen_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, chat_jid)
);

CREATE TABLE IF NOT EXISTS agenda (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  titulo TEXT NOT NULL,
  inicio TEXT NOT NULL,
  fim TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'tentativo',
  contato_origem TEXT,
  message_id TEXT NOT NULL,
  reminder_offset_minutes INTEGER NOT NULL DEFAULT 0,
  pre_reminder_sent_at TEXT,
  reminder_sent_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, message_id)
);
