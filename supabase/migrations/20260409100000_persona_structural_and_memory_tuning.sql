alter table public.persona
  add column if not exists structural_strengths jsonb not null default '[]'::jsonb,
  add column if not exists structural_routines jsonb not null default '[]'::jsonb,
  add column if not exists structural_preferences jsonb not null default '[]'::jsonb,
  add column if not exists structural_open_questions jsonb not null default '[]'::jsonb;

alter table public.automation_settings
  alter column min_new_messages_threshold set default 12;

alter table public.automation_settings
  alter column default_target_message_count set default 120;

update public.automation_settings
set min_new_messages_threshold = 12
where min_new_messages_threshold = 25;

update public.automation_settings
set default_target_message_count = 120
where default_target_message_count = 200;
