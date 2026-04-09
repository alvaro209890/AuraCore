create extension if not exists pgcrypto;

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
