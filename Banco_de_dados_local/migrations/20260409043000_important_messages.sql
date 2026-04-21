create extension if not exists pgcrypto;

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
