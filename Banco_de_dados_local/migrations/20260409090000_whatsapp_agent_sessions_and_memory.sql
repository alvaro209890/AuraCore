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

create table if not exists public.whatsapp_agent_messages (
  id uuid primary key,
  user_id uuid not null,
  thread_id uuid not null references public.whatsapp_agent_threads(id) on delete cascade,
  direction text not null,
  role text not null,
  whatsapp_message_id text,
  source_inbound_message_id text,
  contact_phone text,
  chat_jid text,
  content text not null,
  message_timestamp timestamptz not null,
  processing_status text not null default 'received',
  send_status text,
  error_text text,
  response_latency_ms integer,
  model_run_id uuid,
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

create index if not exists whatsapp_agent_messages_thread_timestamp_idx
  on public.whatsapp_agent_messages (thread_id, message_timestamp desc);

create index if not exists whatsapp_agent_messages_user_thread_timestamp_idx
  on public.whatsapp_agent_messages (user_id, thread_id, message_timestamp desc);

create index if not exists whatsapp_agent_messages_user_contact_phone_idx
  on public.whatsapp_agent_messages (user_id, contact_phone);

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

alter table public.whatsapp_agent_messages
  add column if not exists session_id uuid references public.whatsapp_agent_thread_sessions(id) on delete set null,
  add column if not exists learning_status text not null default 'not_applicable',
  add column if not exists learned_at timestamptz;

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

create index if not exists whatsapp_agent_messages_session_timestamp_idx
  on public.whatsapp_agent_messages (session_id, message_timestamp desc);
