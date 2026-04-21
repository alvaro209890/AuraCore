create table if not exists public.processed_message_ids (
  message_id text primary key,
  user_id uuid not null,
  processed_at timestamptz not null default timezone('utc', now())
);

create index if not exists processed_message_ids_user_processed_idx
  on public.processed_message_ids (user_id, processed_at desc);
