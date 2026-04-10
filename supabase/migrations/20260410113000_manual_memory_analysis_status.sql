alter table public.mensagens
  add column if not exists analysis_status text not null default 'pending',
  add column if not exists analysis_job_id uuid,
  add column if not exists analysis_started_at timestamptz,
  add column if not exists analyzed_at timestamptz;

update public.mensagens
set analysis_status = 'pending'
where analysis_status is null;

create index if not exists mensagens_user_analysis_status_timestamp_idx
  on public.mensagens (user_id, analysis_status, "timestamp" desc);
