create table if not exists public.project_memories (
  id uuid primary key,
  user_id uuid not null,
  project_key text not null,
  project_name text not null,
  summary text not null,
  status text not null default '',
  next_steps jsonb not null default '[]'::jsonb,
  evidence jsonb not null default '[]'::jsonb,
  source_snapshot_id uuid,
  last_seen_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, project_key)
);

create index if not exists project_memories_user_last_seen_idx
  on public.project_memories (user_id, last_seen_at desc nulls last);

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
