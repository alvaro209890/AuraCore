alter table public.mensagens
  add column if not exists contact_phone text,
  add column if not exists direction text,
  add column if not exists source text;

update public.mensagens
set
  contact_phone = coalesce(nullif(contact_phone, ''), contact_name),
  direction = coalesce(nullif(direction, ''), 'inbound'),
  source = coalesce(nullif(source, ''), 'baileys')
where
  contact_phone is null
  or direction is null
  or source is null
  or contact_phone = ''
  or direction = ''
  or source = '';

alter table public.mensagens
  alter column direction set default 'inbound',
  alter column direction set not null,
  alter column source set default 'baileys',
  alter column source set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'mensagens_direction_check'
  ) then
    alter table public.mensagens
      add constraint mensagens_direction_check
      check (direction in ('inbound', 'outbound'));
  end if;
end
$$;

create index if not exists mensagens_user_direction_timestamp_idx
  on public.mensagens (user_id, direction, "timestamp" desc);

alter table public.persona
  add column if not exists last_analyzed_at timestamptz,
  add column if not exists last_snapshot_id uuid;

create table if not exists public.memory_snapshots (
  id uuid primary key,
  user_id uuid not null,
  window_hours integer not null check (window_hours > 0),
  window_start timestamptz not null,
  window_end timestamptz not null,
  source_message_count integer not null default 0 check (source_message_count >= 0),
  window_summary text not null,
  key_learnings jsonb not null default '[]'::jsonb,
  people_and_relationships jsonb not null default '[]'::jsonb,
  routine_signals jsonb not null default '[]'::jsonb,
  preferences jsonb not null default '[]'::jsonb,
  open_questions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists memory_snapshots_user_created_at_idx
  on public.memory_snapshots (user_id, created_at desc);
