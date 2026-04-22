CREATE TABLE IF NOT EXISTS mensagens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  chat_type TEXT NOT NULL DEFAULT 'direct',
  chat_name TEXT,
  contact_name TEXT NOT NULL,
  chat_jid TEXT,
  contact_phone TEXT,
  participant_name TEXT,
  participant_phone TEXT,
  participant_jid TEXT,
  direction TEXT NOT NULL DEFAULT 'inbound',
  message_text TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'baileys',
  embedding TEXT,
  ingested_at TEXT NOT NULL,
  analysis_status TEXT NOT NULL DEFAULT 'pending',
  analysis_job_id TEXT,
  analysis_started_at TEXT,
  analyzed_at TEXT
);

CREATE INDEX IF NOT EXISTS mensagens_user_timestamp_idx ON mensagens (user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS mensagens_user_chat_type_timestamp_idx ON mensagens (user_id, chat_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS mensagens_user_direction_timestamp_idx ON mensagens (user_id, direction, timestamp DESC);
CREATE INDEX IF NOT EXISTS mensagens_user_chat_jid_timestamp_idx ON mensagens (user_id, chat_jid, timestamp DESC);
CREATE INDEX IF NOT EXISTS mensagens_user_contact_phone_timestamp_idx ON mensagens (user_id, contact_phone, timestamp DESC);
CREATE INDEX IF NOT EXISTS mensagens_user_analysis_status_timestamp_idx ON mensagens (user_id, analysis_status, timestamp DESC);

CREATE TABLE IF NOT EXISTS processed_message_ids (
  message_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS processed_message_ids_user_processed_idx ON processed_message_ids (user_id, processed_at DESC);

CREATE TABLE IF NOT EXISTS whatsapp_known_contacts (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  contact_phone TEXT NOT NULL,
  chat_jid TEXT,
  contact_name TEXT NOT NULL DEFAULT '',
  name_source TEXT NOT NULL DEFAULT 'unknown',
  is_admin INTEGER NOT NULL DEFAULT 0,
  last_seen_at TEXT,
  admin_updated_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, contact_phone)
);

CREATE INDEX IF NOT EXISTS whatsapp_known_contacts_user_phone_idx ON whatsapp_known_contacts (user_id, contact_phone);
CREATE INDEX IF NOT EXISTS whatsapp_known_contacts_user_chat_jid_idx ON whatsapp_known_contacts (user_id, chat_jid);
CREATE INDEX IF NOT EXISTS whatsapp_known_contacts_user_seen_idx ON whatsapp_known_contacts (user_id, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS whatsapp_known_contacts_user_admin_idx ON whatsapp_known_contacts (user_id, is_admin, updated_at DESC);

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

CREATE INDEX IF NOT EXISTS whatsapp_known_groups_user_chat_idx ON whatsapp_known_groups (user_id, chat_jid);
CREATE INDEX IF NOT EXISTS whatsapp_known_groups_user_enabled_idx ON whatsapp_known_groups (user_id, enabled_for_analysis, updated_at DESC);
CREATE INDEX IF NOT EXISTS whatsapp_known_groups_user_seen_idx ON whatsapp_known_groups (user_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS persona (
  user_id TEXT PRIMARY KEY,
  life_summary TEXT NOT NULL DEFAULT '',
  last_analyzed_at TEXT,
  last_snapshot_id TEXT,
  last_analyzed_ingested_count INTEGER,
  last_analyzed_pruned_count INTEGER,
  structural_strengths TEXT NOT NULL DEFAULT '[]',
  structural_routines TEXT NOT NULL DEFAULT '[]',
  structural_preferences TEXT NOT NULL DEFAULT '[]',
  structural_open_questions TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_snapshots (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  window_hours INTEGER NOT NULL,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  source_message_count INTEGER NOT NULL DEFAULT 0,
  distinct_contact_count INTEGER NOT NULL DEFAULT 0,
  inbound_message_count INTEGER NOT NULL DEFAULT 0,
  outbound_message_count INTEGER NOT NULL DEFAULT 0,
  coverage_score INTEGER NOT NULL DEFAULT 0,
  window_summary TEXT NOT NULL,
  key_learnings TEXT NOT NULL DEFAULT '[]',
  people_and_relationships TEXT NOT NULL DEFAULT '[]',
  routine_signals TEXT NOT NULL DEFAULT '[]',
  preferences TEXT NOT NULL DEFAULT '[]',
  open_questions TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS memory_snapshots_user_created_at_idx ON memory_snapshots (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS person_memories (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  person_key TEXT NOT NULL,
  contact_name TEXT NOT NULL DEFAULT '',
  contact_phone TEXT,
  chat_jid TEXT,
  profile_summary TEXT NOT NULL DEFAULT '',
  relationship_type TEXT NOT NULL DEFAULT '',
  relationship_summary TEXT NOT NULL DEFAULT '',
  salient_facts TEXT NOT NULL DEFAULT '[]',
  open_loops TEXT NOT NULL DEFAULT '[]',
  recent_topics TEXT NOT NULL DEFAULT '[]',
  source_snapshot_id TEXT,
  source_message_count INTEGER NOT NULL DEFAULT 0,
  last_message_at TEXT,
  last_analyzed_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, person_key)
);

CREATE INDEX IF NOT EXISTS person_memories_user_last_message_idx ON person_memories (user_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS person_memories_user_contact_phone_idx ON person_memories (user_id, contact_phone);
CREATE INDEX IF NOT EXISTS person_memories_user_chat_jid_idx ON person_memories (user_id, chat_jid);

CREATE TABLE IF NOT EXISTS person_memory_snapshots (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  person_memory_id TEXT,
  person_key TEXT NOT NULL,
  contact_name TEXT NOT NULL DEFAULT '',
  contact_phone TEXT,
  chat_jid TEXT,
  source_snapshot_id TEXT,
  profile_summary TEXT NOT NULL DEFAULT '',
  relationship_type TEXT NOT NULL DEFAULT '',
  relationship_summary TEXT NOT NULL DEFAULT '',
  salient_facts TEXT NOT NULL DEFAULT '[]',
  open_loops TEXT NOT NULL DEFAULT '[]',
  recent_topics TEXT NOT NULL DEFAULT '[]',
  source_message_count INTEGER NOT NULL DEFAULT 0,
  window_start TEXT,
  window_end TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (person_memory_id) REFERENCES person_memories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS person_memory_snapshots_user_created_idx ON person_memory_snapshots (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS person_memory_snapshots_user_person_key_idx ON person_memory_snapshots (user_id, person_key, created_at DESC);

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

CREATE INDEX IF NOT EXISTS project_memories_user_last_seen_idx ON project_memories (user_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS chat_threads (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  thread_key TEXT NOT NULL,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, thread_key)
);

CREATE INDEX IF NOT EXISTS chat_threads_user_updated_idx ON chat_threads (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chat_messages_thread_created_idx ON chat_messages (thread_id, created_at DESC);

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
  recurrence_rule TEXT,
  parent_event_id TEXT,
  excluded_dates TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, message_id)
);

CREATE INDEX IF NOT EXISTS agenda_user_inicio_idx ON agenda (user_id, inicio ASC);
CREATE INDEX IF NOT EXISTS agenda_user_fim_idx ON agenda (user_id, fim ASC);
CREATE INDEX IF NOT EXISTS agenda_user_status_inicio_idx ON agenda (user_id, status, inicio ASC);

CREATE TABLE IF NOT EXISTS whatsapp_agent_settings (
  user_id TEXT PRIMARY KEY,
  auto_reply_enabled INTEGER NOT NULL DEFAULT 0,
  allowed_contact_phone TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS whatsapp_agent_threads (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  contact_phone TEXT,
  chat_jid TEXT,
  contact_name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  last_message_at TEXT,
  last_inbound_at TEXT,
  last_outbound_at TEXT,
  last_error_at TEXT,
  last_error_text TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, contact_phone)
);

CREATE INDEX IF NOT EXISTS whatsapp_agent_threads_user_last_message_idx ON whatsapp_agent_threads (user_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS whatsapp_agent_threads_user_contact_phone_idx ON whatsapp_agent_threads (user_id, contact_phone);
CREATE INDEX IF NOT EXISTS whatsapp_agent_threads_user_chat_jid_idx ON whatsapp_agent_threads (user_id, chat_jid);

CREATE TABLE IF NOT EXISTS whatsapp_agent_thread_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  contact_phone TEXT,
  chat_jid TEXT,
  started_at TEXT NOT NULL,
  last_activity_at TEXT NOT NULL,
  ended_at TEXT,
  reset_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (thread_id) REFERENCES whatsapp_agent_threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS whatsapp_agent_thread_sessions_user_thread_idx ON whatsapp_agent_thread_sessions (user_id, thread_id, last_activity_at DESC);
CREATE INDEX IF NOT EXISTS whatsapp_agent_thread_sessions_user_contact_idx ON whatsapp_agent_thread_sessions (user_id, contact_phone, last_activity_at DESC);
CREATE INDEX IF NOT EXISTS whatsapp_agent_thread_sessions_active_idx ON whatsapp_agent_thread_sessions (thread_id, last_activity_at DESC);

CREATE TABLE IF NOT EXISTS whatsapp_agent_terminal_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  contact_phone TEXT,
  chat_jid TEXT,
  cli_mode_enabled INTEGER NOT NULL DEFAULT 0,
  cwd TEXT NOT NULL,
  context_version INTEGER NOT NULL DEFAULT 1,
  last_command_text TEXT,
  last_command_at TEXT,
  pending_command_text TEXT,
  pending_plan_json TEXT NOT NULL DEFAULT '{}',
  pending_requested_at TEXT,
  session_summary TEXT NOT NULL DEFAULT '',
  last_discovery_summary TEXT NOT NULL DEFAULT '',
  context_metadata TEXT NOT NULL DEFAULT '{}',
  closed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, thread_id),
  FOREIGN KEY (thread_id) REFERENCES whatsapp_agent_threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS whatsapp_agent_terminal_sessions_user_thread_idx ON whatsapp_agent_terminal_sessions (user_id, thread_id);
CREATE INDEX IF NOT EXISTS whatsapp_agent_terminal_sessions_user_contact_idx ON whatsapp_agent_terminal_sessions (user_id, contact_phone, updated_at DESC);

CREATE TABLE IF NOT EXISTS whatsapp_agent_messages (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  role TEXT NOT NULL,
  session_id TEXT,
  whatsapp_message_id TEXT,
  source_inbound_message_id TEXT,
  contact_phone TEXT,
  chat_jid TEXT,
  content TEXT NOT NULL,
  message_timestamp TEXT NOT NULL,
  processing_status TEXT NOT NULL DEFAULT 'received',
  learning_status TEXT NOT NULL DEFAULT 'not_applicable',
  send_status TEXT,
  error_text TEXT,
  response_latency_ms INTEGER,
  model_run_id TEXT,
  learned_at TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE (user_id, whatsapp_message_id),
  UNIQUE (user_id, source_inbound_message_id),
  FOREIGN KEY (thread_id) REFERENCES whatsapp_agent_threads(id) ON DELETE CASCADE,
  FOREIGN KEY (session_id) REFERENCES whatsapp_agent_thread_sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS whatsapp_agent_messages_thread_timestamp_idx ON whatsapp_agent_messages (thread_id, message_timestamp DESC);
CREATE INDEX IF NOT EXISTS whatsapp_agent_messages_user_thread_timestamp_idx ON whatsapp_agent_messages (user_id, thread_id, message_timestamp DESC);
CREATE INDEX IF NOT EXISTS whatsapp_agent_messages_user_contact_phone_idx ON whatsapp_agent_messages (user_id, contact_phone);
CREATE INDEX IF NOT EXISTS whatsapp_agent_messages_session_timestamp_idx ON whatsapp_agent_messages (session_id, message_timestamp DESC);

CREATE TABLE IF NOT EXISTS whatsapp_agent_contact_memories (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  thread_id TEXT,
  contact_phone TEXT NOT NULL,
  chat_jid TEXT,
  contact_name TEXT NOT NULL DEFAULT '',
  profile_summary TEXT NOT NULL DEFAULT '',
  preferred_tone TEXT NOT NULL DEFAULT '',
  preferences TEXT NOT NULL DEFAULT '[]',
  objectives TEXT NOT NULL DEFAULT '[]',
  durable_facts TEXT NOT NULL DEFAULT '[]',
  constraints TEXT NOT NULL DEFAULT '[]',
  recurring_instructions TEXT NOT NULL DEFAULT '[]',
  learned_message_count INTEGER NOT NULL DEFAULT 0,
  last_learned_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, contact_phone),
  FOREIGN KEY (thread_id) REFERENCES whatsapp_agent_threads(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS whatsapp_agent_contact_memories_user_thread_idx ON whatsapp_agent_contact_memories (user_id, thread_id);
CREATE INDEX IF NOT EXISTS whatsapp_agent_contact_memories_user_contact_idx ON whatsapp_agent_contact_memories (user_id, contact_phone);

CREATE TABLE IF NOT EXISTS message_retention_state (
  user_id TEXT PRIMARY KEY,
  total_direct_ingested_count INTEGER NOT NULL DEFAULT 0,
  total_direct_pruned_count INTEGER NOT NULL DEFAULT 0,
  observer_history_cutoff_at TEXT,
  last_message_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_settings (
  user_id TEXT PRIMARY KEY,
  auto_sync_enabled INTEGER NOT NULL DEFAULT 1,
  auto_analyze_enabled INTEGER NOT NULL DEFAULT 1,
  auto_refine_enabled INTEGER NOT NULL DEFAULT 0,
  min_new_messages_threshold INTEGER NOT NULL DEFAULT 20,
  stale_hours_threshold INTEGER NOT NULL DEFAULT 24,
  pruned_messages_threshold INTEGER NOT NULL DEFAULT 1,
  default_detail_mode TEXT NOT NULL DEFAULT 'balanced',
  default_target_message_count INTEGER NOT NULL DEFAULT 20,
  default_lookback_hours INTEGER NOT NULL DEFAULT 72,
  daily_budget_usd REAL NOT NULL DEFAULT 5.0,
  max_auto_jobs_per_day INTEGER NOT NULL DEFAULT 100,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wa_sync_runs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  trigger TEXT NOT NULL,
  status TEXT NOT NULL,
  messages_seen_count INTEGER NOT NULL DEFAULT 0,
  messages_saved_count INTEGER NOT NULL DEFAULT 0,
  messages_ignored_count INTEGER NOT NULL DEFAULT 0,
  messages_pruned_count INTEGER NOT NULL DEFAULT 0,
  oldest_message_at TEXT,
  newest_message_at TEXT,
  error_text TEXT,
  baseline_ingested_count INTEGER NOT NULL DEFAULT 0,
  baseline_pruned_count INTEGER NOT NULL DEFAULT 0,
  last_activity_at TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE INDEX IF NOT EXISTS wa_sync_runs_user_started_idx ON wa_sync_runs (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS wa_sync_runs_user_status_started_idx ON wa_sync_runs (user_id, status, started_at DESC);

CREATE TABLE IF NOT EXISTS automation_decisions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  sync_run_id TEXT,
  intent TEXT NOT NULL,
  action TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  score INTEGER NOT NULL DEFAULT 0,
  should_analyze INTEGER NOT NULL DEFAULT 0,
  available_message_count INTEGER NOT NULL DEFAULT 0,
  selected_message_count INTEGER NOT NULL DEFAULT 0,
  new_message_count INTEGER NOT NULL DEFAULT 0,
  replaced_message_count INTEGER NOT NULL DEFAULT 0,
  estimated_total_tokens INTEGER NOT NULL DEFAULT 0,
  estimated_cost_ceiling_usd REAL NOT NULL DEFAULT 0,
  explanation TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS automation_decisions_user_created_idx ON automation_decisions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS analysis_jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  intent TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger_source TEXT NOT NULL,
  decision_id TEXT,
  sync_run_id TEXT,
  target_message_count INTEGER NOT NULL DEFAULT 0,
  max_lookback_hours INTEGER NOT NULL DEFAULT 0,
  detail_mode TEXT NOT NULL DEFAULT 'balanced',
  selected_message_count INTEGER NOT NULL DEFAULT 0,
  selected_transcript_chars INTEGER NOT NULL DEFAULT 0,
  estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
  estimated_output_tokens INTEGER NOT NULL DEFAULT 0,
  estimated_cost_floor_usd REAL NOT NULL DEFAULT 0,
  estimated_cost_ceiling_usd REAL NOT NULL DEFAULT 0,
  snapshot_id TEXT,
  error_text TEXT,
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS analysis_jobs_user_created_idx ON analysis_jobs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS analysis_jobs_user_status_created_idx ON analysis_jobs (user_id, status, created_at ASC);

CREATE TABLE IF NOT EXISTS analysis_job_messages (
  job_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (job_id, message_id),
  FOREIGN KEY (job_id) REFERENCES analysis_jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_runs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  job_id TEXT,
  provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  run_type TEXT NOT NULL,
  success INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  input_tokens INTEGER,
  output_tokens INTEGER,
  reasoning_tokens INTEGER,
  estimated_cost_usd REAL,
  error_text TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS model_runs_user_created_idx ON model_runs (user_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS important_messages_user_timestamp_idx ON important_messages (user_id, message_timestamp DESC);
CREATE INDEX IF NOT EXISTS important_messages_user_status_timestamp_idx ON important_messages (user_id, status, message_timestamp DESC);
CREATE INDEX IF NOT EXISTS important_messages_user_contact_idx ON important_messages (user_id, contact_phone, message_timestamp DESC);

CREATE TABLE IF NOT EXISTS proactive_preferences (
  user_id TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 1,
  intensity TEXT NOT NULL DEFAULT 'moderate',
  presence_mode TEXT NOT NULL DEFAULT 'organic',
  humor_style TEXT NOT NULL DEFAULT 'subtle',
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

CREATE INDEX IF NOT EXISTS proactive_candidates_user_status_due_idx ON proactive_candidates (user_id, status, due_at ASC);
CREATE INDEX IF NOT EXISTS proactive_candidates_user_category_updated_idx ON proactive_candidates (user_id, category, updated_at DESC);
CREATE INDEX IF NOT EXISTS proactive_candidates_user_contact_updated_idx ON proactive_candidates (user_id, contact_phone, updated_at DESC);

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

CREATE INDEX IF NOT EXISTS proactive_delivery_log_user_created_idx ON proactive_delivery_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS proactive_delivery_log_user_category_created_idx ON proactive_delivery_log (user_id, category, created_at DESC);

CREATE TABLE IF NOT EXISTS proactive_digest_state (
  user_id TEXT PRIMARY KEY,
  last_morning_digest_at TEXT,
  last_night_digest_at TEXT,
  last_morning_digest_signature TEXT NOT NULL DEFAULT '',
  last_night_digest_signature TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wa_sessions (
  session_id TEXT PRIMARY KEY,
  creds TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wa_session_keys (
  session_id TEXT NOT NULL,
  category TEXT NOT NULL,
  key_id TEXT NOT NULL,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (session_id, category, key_id)
);

CREATE INDEX IF NOT EXISTS wa_session_keys_session_category_idx ON wa_session_keys (session_id, category);
