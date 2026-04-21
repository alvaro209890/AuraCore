alter table public.automation_settings
  alter column min_new_messages_threshold set default 20;

update public.automation_settings
set min_new_messages_threshold = 20
where min_new_messages_threshold is distinct from 20;
