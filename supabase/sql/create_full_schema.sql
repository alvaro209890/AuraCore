create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists public.mensagens (
  id text primary key,
  user_id uuid not null,
  contact_name text not null,
  chat_jid text,
  contact_phone text,
  direction text not null default 'inbound',
  message_text text not null,
  "timestamp" timestamptz not null,
  source text not null default 'baileys',
  embedding vector(1536),
  ingested_at timestamptz not null default timezone('utc', now())
);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'mensagens_direction_check'
  ) then
    alter table public.mensagens
      add constraint mensagens_direction_check
      check (direction in ('inbound', 'outbound'));
  end if;
end
$$;

create index if not exists mensagens_user_timestamp_idx
  on public.mensagens (user_id, "timestamp" desc);

create index if not exists mensagens_user_direction_timestamp_idx
  on public.mensagens (user_id, direction, "timestamp" desc);

create index if not exists mensagens_user_chat_jid_timestamp_idx
  on public.mensagens (user_id, chat_jid, "timestamp" desc);

create index if not exists mensagens_user_contact_phone_timestamp_idx
  on public.mensagens (user_id, contact_phone, "timestamp" desc);

create table if not exists public.processed_message_ids (
  message_id text primary key,
  user_id uuid not null,
  processed_at timestamptz not null default timezone('utc', now())
);

create index if not exists processed_message_ids_user_processed_idx
  on public.processed_message_ids (user_id, processed_at desc);

create table if not exists public.whatsapp_known_contacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  contact_phone text not null,
  chat_jid text,
  contact_name text not null default '',
  name_source text not null default 'unknown',
  last_seen_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, contact_phone)
);

create index if not exists whatsapp_known_contacts_user_phone_idx
  on public.whatsapp_known_contacts (user_id, contact_phone);

create index if not exists whatsapp_known_contacts_user_chat_jid_idx
  on public.whatsapp_known_contacts (user_id, chat_jid);

create index if not exists whatsapp_known_contacts_user_seen_idx
  on public.whatsapp_known_contacts (user_id, last_seen_at desc nulls last);

create table if not exists public.persona (
  user_id uuid primary key,
  life_summary text not null default '',
  last_analyzed_at timestamptz,
  last_snapshot_id uuid,
  last_analyzed_ingested_count bigint,
  last_analyzed_pruned_count bigint,
  structural_strengths jsonb not null default '[]'::jsonb,
  structural_routines jsonb not null default '[]'::jsonb,
  structural_preferences jsonb not null default '[]'::jsonb,
  structural_open_questions jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.memory_snapshots (
  id uuid primary key,
  user_id uuid not null,
  window_hours integer not null check (window_hours > 0),
  window_start timestamptz not null,
  window_end timestamptz not null,
  source_message_count integer not null default 0 check (source_message_count >= 0),
  window_summary text not null,
  key_learnings jsonb not null default '[]'::jsonb,
  people_and_relationships jsonb not null default '[]'::jsonb,
  routine_signals jsonb not null default '[]'::jsonb,
  preferences jsonb not null default '[]'::jsonb,
  open_questions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists memory_snapshots_user_created_at_idx
  on public.memory_snapshots (user_id, created_at desc);

create table if not exists public.person_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  person_key text not null,
  contact_name text not null default '',
  contact_phone text,
  chat_jid text,
  profile_summary text not null default '',
  relationship_summary text not null default '',
  salient_facts jsonb not null default '[]'::jsonb,
  open_loops jsonb not null default '[]'::jsonb,
  recent_topics jsonb not null default '[]'::jsonb,
  source_snapshot_id uuid,
  source_message_count bigint not null default 0,
  last_message_at timestamptz,
  last_analyzed_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, person_key)
);

create index if not exists person_memories_user_last_message_idx
  on public.person_memories (user_id, last_message_at desc nulls last);

create index if not exists person_memories_user_contact_phone_idx
  on public.person_memories (user_id, contact_phone);

create index if not exists person_memories_user_chat_jid_idx
  on public.person_memories (user_id, chat_jid);

create table if not exists public.person_memory_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  person_memory_id uuid references public.person_memories(id) on delete set null,
  person_key text not null,
  contact_name text not null default '',
  contact_phone text,
  chat_jid text,
  source_snapshot_id uuid,
  profile_summary text not null default '',
  relationship_summary text not null default '',
  salient_facts jsonb not null default '[]'::jsonb,
  open_loops jsonb not null default '[]'::jsonb,
  recent_topics jsonb not null default '[]'::jsonb,
  source_message_count integer not null default 0,
  window_start timestamptz,
  window_end timestamptz,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists person_memory_snapshots_user_created_idx
  on public.person_memory_snapshots (user_id, created_at desc);

create index if not exists person_memory_snapshots_user_person_key_idx
  on public.person_memory_snapshots (user_id, person_key, created_at desc);

create table if not exists public.project_memories (
  id uuid primary key,
  user_id uuid not null,
  project_key text not null,
  project_name text not null,
  summary text not null,
  status text not null default '',
  what_is_being_built text not null default '',
  built_for text not null default '',
  next_steps jsonb not null default '[]'::jsonb,
  evidence jsonb not null default '[]'::jsonb,
  source_snapshot_id uuid,
  last_seen_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, project_key)
);

create index if not exists project_memories_user_last_seen_idx
  on public.project_memories (user_id, last_seen_at desc nulls last);

create table if not exists public.important_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  source_message_id text not null,
  contact_name text not null default '',
  contact_phone text,
  direction text not null default 'inbound',
  message_text text not null,
  message_timestamp timestamptz not null,
  category text not null default 'other',
  importance_reason text not null default '',
  confidence integer not null default 0,
  status text not null default 'active',
  review_notes text,
  saved_at timestamptz not null default timezone('utc', now()),
  last_reviewed_at timestamptz,
  discarded_at timestamptz,
  unique (user_id, source_message_id)
);

create index if not exists important_messages_user_status_timestamp_idx
  on public.important_messages (user_id, status, message_timestamp desc);

create index if not exists important_messages_user_review_idx
  on public.important_messages (user_id, last_reviewed_at asc);

create table if not exists public.chat_threads (
  id uuid primary key,
  user_id uuid not null,
  thread_key text not null,
  title text not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, thread_key)
);

create index if not exists chat_threads_user_updated_idx
  on public.chat_threads (user_id, updated_at desc);

create table if not exists public.chat_messages (
  id uuid primary key,
  thread_id uuid not null references public.chat_threads(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists chat_messages_thread_created_idx
  on public.chat_messages (thread_id, created_at desc);

create table if not exists public.whatsapp_agent_settings (
  user_id uuid primary key,
  auto_reply_enabled boolean not null default false,
  allowed_contact_phone text,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.whatsapp_agent_threads (
  id uuid primary key,
  user_id uuid not null,
  contact_phone text,
  chat_jid text,
  contact_name text not null default '',
  status text not null default 'active',
  last_message_at timestamptz,
  last_inbound_at timestamptz,
  last_outbound_at timestamptz,
  last_error_at timestamptz,
  last_error_text text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, contact_phone)
);

create index if not exists whatsapp_agent_threads_user_last_message_idx
  on public.whatsapp_agent_threads (user_id, last_message_at desc nulls last);

create index if not exists whatsapp_agent_threads_user_contact_phone_idx
  on public.whatsapp_agent_threads (user_id, contact_phone);

create index if not exists whatsapp_agent_threads_user_chat_jid_idx
  on public.whatsapp_agent_threads (user_id, chat_jid);

create table if not exists public.whatsapp_agent_thread_sessions (
  id uuid primary key,
  user_id uuid not null,
  thread_id uuid not null references public.whatsapp_agent_threads(id) on delete cascade,
  contact_phone text,
  chat_jid text,
  started_at timestamptz not null,
  last_activity_at timestamptz not null,
  ended_at timestamptz,
  reset_reason text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists whatsapp_agent_thread_sessions_user_thread_idx
  on public.whatsapp_agent_thread_sessions (user_id, thread_id, last_activity_at desc);

create index if not exists whatsapp_agent_thread_sessions_user_contact_idx
  on public.whatsapp_agent_thread_sessions (user_id, contact_phone, last_activity_at desc);

create index if not exists whatsapp_agent_thread_sessions_active_idx
  on public.whatsapp_agent_thread_sessions (thread_id, last_activity_at desc)
  where ended_at is null;

create table if not exists public.whatsapp_agent_messages (
  id uuid primary key,
  user_id uuid not null,
  thread_id uuid not null references public.whatsapp_agent_threads(id) on delete cascade,
  direction text not null,
  role text not null,
  session_id uuid references public.whatsapp_agent_thread_sessions(id) on delete set null,
  whatsapp_message_id text,
  source_inbound_message_id text,
  contact_phone text,
  chat_jid text,
  content text not null,
  message_timestamp timestamptz not null,
  processing_status text not null default 'received',
  learning_status text not null default 'not_applicable',
  send_status text,
  error_text text,
  response_latency_ms integer,
  model_run_id uuid,
  learned_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  unique (user_id, whatsapp_message_id),
  unique (user_id, source_inbound_message_id)
);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'whatsapp_agent_messages_direction_check'
  ) then
    alter table public.whatsapp_agent_messages
      add constraint whatsapp_agent_messages_direction_check
      check (direction in ('inbound', 'outbound'));
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'whatsapp_agent_messages_role_check'
  ) then
    alter table public.whatsapp_agent_messages
      add constraint whatsapp_agent_messages_role_check
      check (role in ('user', 'assistant'));
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'whatsapp_agent_messages_learning_status_check'
  ) then
    alter table public.whatsapp_agent_messages
      add constraint whatsapp_agent_messages_learning_status_check
      check (
        learning_status in (
          'not_applicable',
          'pending_review',
          'not_relevant',
          'reviewed_no_update',
          'learned',
          'failed'
        )
      );
  end if;
end
$$;

create index if not exists whatsapp_agent_messages_thread_timestamp_idx
  on public.whatsapp_agent_messages (thread_id, message_timestamp desc);

create index if not exists whatsapp_agent_messages_user_thread_timestamp_idx
  on public.whatsapp_agent_messages (user_id, thread_id, message_timestamp desc);

create index if not exists whatsapp_agent_messages_user_contact_phone_idx
  on public.whatsapp_agent_messages (user_id, contact_phone);

create index if not exists whatsapp_agent_messages_session_timestamp_idx
  on public.whatsapp_agent_messages (session_id, message_timestamp desc);

create table if not exists public.whatsapp_agent_contact_memories (
  id uuid primary key,
  user_id uuid not null,
  thread_id uuid references public.whatsapp_agent_threads(id) on delete set null,
  contact_phone text not null,
  chat_jid text,
  contact_name text not null default '',
  profile_summary text not null default '',
  preferred_tone text not null default '',
  preferences jsonb not null default '[]'::jsonb,
  objectives jsonb not null default '[]'::jsonb,
  durable_facts jsonb not null default '[]'::jsonb,
  constraints jsonb not null default '[]'::jsonb,
  recurring_instructions jsonb not null default '[]'::jsonb,
  learned_message_count integer not null default 0 check (learned_message_count >= 0),
  last_learned_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, contact_phone)
);

create index if not exists whatsapp_agent_contact_memories_user_thread_idx
  on public.whatsapp_agent_contact_memories (user_id, thread_id);

create index if not exists whatsapp_agent_contact_memories_user_contact_idx
  on public.whatsapp_agent_contact_memories (user_id, contact_phone);

create table if not exists public.message_retention_state (
  user_id uuid primary key,
  total_direct_ingested_count bigint not null default 0,
  total_direct_pruned_count bigint not null default 0,
  observer_history_cutoff_at timestamptz,
  last_message_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.automation_settings (
  user_id uuid primary key,
  auto_sync_enabled boolean not null default true,
  auto_analyze_enabled boolean not null default true,
  auto_refine_enabled boolean not null default false,
  min_new_messages_threshold integer not null default 12,
  stale_hours_threshold integer not null default 24,
  pruned_messages_threshold integer not null default 1,
  default_detail_mode text not null default 'balanced',
  default_target_message_count integer not null default 120,
  default_lookback_hours integer not null default 72,
  daily_budget_usd numeric(12,6) not null default 0.250000,
  max_auto_jobs_per_day integer not null default 4,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.wa_sync_runs (
  id uuid primary key,
  user_id uuid not null,
  trigger text not null,
  status text not null,
  messages_seen_count integer not null default 0,
  messages_saved_count integer not null default 0,
  messages_ignored_count integer not null default 0,
  messages_pruned_count integer not null default 0,
  oldest_message_at timestamptz,
  newest_message_at timestamptz,
  error_text text,
  baseline_ingested_count bigint not null default 0,
  baseline_pruned_count bigint not null default 0,
  last_activity_at timestamptz,
  started_at timestamptz not null default timezone('utc', now()),
  finished_at timestamptz
);

create index if not exists wa_sync_runs_user_started_idx
  on public.wa_sync_runs (user_id, started_at desc);

create index if not exists wa_sync_runs_user_status_started_idx
  on public.wa_sync_runs (user_id, status, started_at desc);

create table if not exists public.automation_decisions (
  id uuid primary key,
  user_id uuid not null,
  sync_run_id uuid,
  intent text not null,
  action text not null,
  reason_code text not null,
  score integer not null default 0,
  should_analyze boolean not null default false,
  available_message_count integer not null default 0,
  selected_message_count integer not null default 0,
  new_message_count integer not null default 0,
  replaced_message_count integer not null default 0,
  estimated_total_tokens integer not null default 0,
  estimated_cost_ceiling_usd numeric(12,6) not null default 0,
  explanation text not null default '',
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists automation_decisions_user_created_idx
  on public.automation_decisions (user_id, created_at desc);

create table if not exists public.analysis_jobs (
  id uuid primary key,
  user_id uuid not null,
  intent text not null,
  status text not null,
  trigger_source text not null,
  decision_id uuid,
  sync_run_id uuid,
  target_message_count integer not null default 0,
  max_lookback_hours integer not null default 0,
  detail_mode text not null default 'balanced',
  selected_message_count integer not null default 0,
  selected_transcript_chars integer not null default 0,
  estimated_input_tokens integer not null default 0,
  estimated_output_tokens integer not null default 0,
  estimated_cost_floor_usd numeric(12,6) not null default 0,
  estimated_cost_ceiling_usd numeric(12,6) not null default 0,
  snapshot_id uuid,
  error_text text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists analysis_jobs_user_created_idx
  on public.analysis_jobs (user_id, created_at desc);

create index if not exists analysis_jobs_user_status_created_idx
  on public.analysis_jobs (user_id, status, created_at asc);

create table if not exists public.analysis_job_messages (
  job_id uuid not null references public.analysis_jobs(id) on delete cascade,
  message_id text not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (job_id, message_id)
);

create table if not exists public.model_runs (
  id uuid primary key,
  user_id uuid not null,
  job_id uuid,
  provider text not null,
  model_name text not null,
  run_type text not null,
  success boolean not null default false,
  latency_ms integer,
  input_tokens integer,
  output_tokens integer,
  reasoning_tokens integer,
  estimated_cost_usd numeric(12,6),
  error_text text,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists model_runs_user_created_idx
  on public.model_runs (user_id, created_at desc);

create table if not exists public.wa_sessions (
  session_id text primary key,
  creds jsonb not null,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.wa_session_keys (
  session_id text not null,
  category text not null,
  key_id text not null,
  value jsonb not null,
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (session_id, category, key_id)
);

create index if not exists wa_session_keys_session_category_idx
  on public.wa_session_keys (session_id, category);
