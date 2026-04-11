alter table public.mensagens
  add column if not exists chat_type text not null default 'direct',
  add column if not exists chat_name text,
  add column if not exists participant_name text,
  add column if not exists participant_phone text,
  add column if not exists participant_jid text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'mensagens_chat_type_check'
  ) then
    alter table public.mensagens
      add constraint mensagens_chat_type_check
      check (chat_type in ('direct', 'group'));
  end if;
end
$$;

create index if not exists mensagens_user_chat_type_timestamp_idx
  on public.mensagens (user_id, chat_type, "timestamp" desc);

create table if not exists public.whatsapp_known_groups (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  chat_jid text not null,
  chat_name text not null default '',
  enabled_for_analysis boolean not null default false,
  last_seen_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, chat_jid)
);

create index if not exists whatsapp_known_groups_user_chat_idx
  on public.whatsapp_known_groups (user_id, chat_jid);

create index if not exists whatsapp_known_groups_user_enabled_idx
  on public.whatsapp_known_groups (user_id, enabled_for_analysis, updated_at desc);

create index if not exists whatsapp_known_groups_user_seen_idx
  on public.whatsapp_known_groups (user_id, last_seen_at desc nulls last);
