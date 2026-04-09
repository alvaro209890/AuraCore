create table if not exists public.whatsapp_known_contacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  contact_phone text not null,
  chat_jid text,
  contact_name text not null default '',
  name_source text not null default 'unknown',
  last_seen_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (user_id, contact_phone)
);

create index if not exists whatsapp_known_contacts_user_phone_idx
  on public.whatsapp_known_contacts (user_id, contact_phone);

create index if not exists whatsapp_known_contacts_user_chat_jid_idx
  on public.whatsapp_known_contacts (user_id, chat_jid);

create index if not exists whatsapp_known_contacts_user_seen_idx
  on public.whatsapp_known_contacts (user_id, last_seen_at desc nulls last);

alter table public.message_retention_state
  add column if not exists observer_history_cutoff_at timestamptz;
