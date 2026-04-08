create extension if not exists vector;

create table if not exists public.mensagens (
  id text primary key,
  user_id uuid not null,
  contact_name text not null,
  message_text text not null,
  "timestamp" timestamptz not null,
  embedding vector(1536)
);

create index if not exists mensagens_user_timestamp_idx
  on public.mensagens (user_id, "timestamp" desc);

create table if not exists public.persona (
  user_id uuid primary key,
  life_summary text not null default '',
  updated_at timestamptz not null default timezone('utc', now())
);
