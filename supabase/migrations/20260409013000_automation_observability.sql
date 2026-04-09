alter table public.mensagens
  add column if not exists chat_jid text,
  add column if not exists ingested_at timestamptz not null default timezone('utc', now());

create index if not exists mensagens_user_chat_jid_timestamp_idx
  on public.mensagens (user_id, chat_jid, "timestamp" desc);

create index if not exists mensagens_user_contact_phone_timestamp_idx
  on public.mensagens (user_id, contact_phone, "timestamp" desc);

create table if not exists public.automation_settings (
  user_id uuid primary key,
  auto_sync_enabled boolean not null default true,
  auto_analyze_enabled boolean not null default true,
  auto_refine_enabled boolean not null default false,
  min_new_messages_threshold integer not null default 25,
  stale_hours_threshold integer not null default 24,
  pruned_messages_threshold integer not null default 1,
  default_detail_mode text not null default 'balanced',
  default_target_message_count integer not null default 200,
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
  job_id uuid not null,
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

insert into public.automation_settings (
  user_id,
  auto_sync_enabled,
  auto_analyze_enabled,
  auto_refine_enabled,
  min_new_messages_threshold,
  stale_hours_threshold,
  pruned_messages_threshold,
  default_detail_mode,
  default_target_message_count,
  default_lookback_hours,
  daily_budget_usd,
  max_auto_jobs_per_day,
  updated_at
)
select
  p.user_id,
  true,
  true,
  false,
  25,
  24,
  1,
  'balanced',
  200,
  72,
  0.250000,
  4,
  timezone('utc', now())
from public.persona p
on conflict (user_id) do nothing;
