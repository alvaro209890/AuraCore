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

CREATE TABLE IF NOT EXISTS project_memories (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  project_key TEXT NOT NULL,
  project_name TEXT NOT NULL,
  origin_source TEXT NOT NULL DEFAULT 'memory',
  summary TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '',
  what_is_being_built TEXT NOT NULL DEFAULT '',
  built_for TEXT NOT NULL DEFAULT '',
  next_steps TEXT NOT NULL DEFAULT '[]',
  evidence TEXT NOT NULL DEFAULT '[]',
  aliases TEXT NOT NULL DEFAULT '[]',
  stage TEXT NOT NULL DEFAULT '',
  priority TEXT NOT NULL DEFAULT '',
  blockers TEXT NOT NULL DEFAULT '[]',
  confidence_score INTEGER NOT NULL DEFAULT 0,
  source_snapshot_id TEXT,
  last_seen_at TEXT,
  last_material_update_at TEXT,
  completion_source TEXT NOT NULL DEFAULT '',
  manual_completed_at TEXT,
  manual_completion_notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, project_key)
);

CREATE TABLE IF NOT EXISTS important_messages (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  source_message_id TEXT NOT NULL,
  contact_name TEXT NOT NULL DEFAULT '',
  contact_phone TEXT,
  direction TEXT NOT NULL DEFAULT 'inbound',
  message_text TEXT NOT NULL,
  message_timestamp TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'other',
  importance_reason TEXT NOT NULL DEFAULT '',
  confidence INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  review_notes TEXT,
  saved_at TEXT NOT NULL,
  last_reviewed_at TEXT,
  discarded_at TEXT,
  UNIQUE (user_id, source_message_id)
);

CREATE TABLE IF NOT EXISTS proactive_preferences (
  user_id TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 1,
  intensity TEXT NOT NULL DEFAULT 'moderate',
  quiet_hours_start TEXT NOT NULL DEFAULT '22:00',
  quiet_hours_end TEXT NOT NULL DEFAULT '08:00',
  max_unsolicited_per_day INTEGER NOT NULL DEFAULT 4,
  min_interval_minutes INTEGER NOT NULL DEFAULT 90,
  agenda_enabled INTEGER NOT NULL DEFAULT 1,
  followups_enabled INTEGER NOT NULL DEFAULT 1,
  projects_enabled INTEGER NOT NULL DEFAULT 1,
  routine_enabled INTEGER NOT NULL DEFAULT 1,
  morning_digest_enabled INTEGER NOT NULL DEFAULT 1,
  night_digest_enabled INTEGER NOT NULL DEFAULT 1,
  morning_digest_time TEXT NOT NULL DEFAULT '08:30',
  night_digest_time TEXT NOT NULL DEFAULT '20:30',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proactive_candidates (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'suggested',
  source_message_id TEXT,
  source_kind TEXT NOT NULL DEFAULT 'heuristic',
  thread_id TEXT,
  contact_phone TEXT,
  chat_jid TEXT,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  confidence INTEGER NOT NULL DEFAULT 0,
  priority INTEGER NOT NULL DEFAULT 0,
  due_at TEXT,
  cooldown_until TEXT,
  last_nudged_at TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proactive_delivery_log (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  candidate_id TEXT,
  category TEXT NOT NULL,
  decision TEXT NOT NULL,
  score INTEGER NOT NULL DEFAULT 0,
  reason_code TEXT NOT NULL DEFAULT '',
  reason_text TEXT NOT NULL DEFAULT '',
  message_text TEXT NOT NULL DEFAULT '',
  message_id TEXT,
  sent_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proactive_digest_state (
  user_id TEXT PRIMARY KEY,
  last_morning_digest_at TEXT,
  last_night_digest_at TEXT,
  last_morning_digest_signature TEXT NOT NULL DEFAULT '',
  last_night_digest_signature TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
