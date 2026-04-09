alter table public.project_memories
  add column if not exists what_is_being_built text not null default '',
  add column if not exists built_for text not null default '';

create table if not exists public.message_retention_state (
  user_id uuid primary key,
  total_direct_ingested_count bigint not null default 0,
  total_direct_pruned_count bigint not null default 0,
  last_message_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now())
);

insert into public.message_retention_state (
  user_id,
  total_direct_ingested_count,
  total_direct_pruned_count,
  last_message_at,
  updated_at
)
select
  m.user_id,
  count(*)::bigint as total_direct_ingested_count,
  0::bigint as total_direct_pruned_count,
  max(m."timestamp") as last_message_at,
  timezone('utc', now()) as updated_at
from public.mensagens m
group by m.user_id
on conflict (user_id) do nothing;

alter table public.persona
  add column if not exists last_analyzed_ingested_count bigint,
  add column if not exists last_analyzed_pruned_count bigint;

update public.persona p
set
  last_analyzed_ingested_count = coalesce(p.last_analyzed_ingested_count, s.total_direct_ingested_count),
  last_analyzed_pruned_count = coalesce(p.last_analyzed_pruned_count, s.total_direct_pruned_count)
from public.message_retention_state s
where p.user_id = s.user_id;
