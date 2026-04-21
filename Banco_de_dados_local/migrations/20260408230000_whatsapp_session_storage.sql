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
