-- Read-only checks for 20261019_flashcards_and_tasks.sql.
select to_regclass('public.flashcards') as flashcards_relation;
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public'
  and table_name in ('flashcards', 'study_plans', 'study_tasks')
order by table_name, ordinal_position;
select indexname
from pg_indexes
where schemaname = 'public'
  and indexname = 'flashcards_user_review_idx';
select indexname
from pg_indexes
where schemaname = 'public'
  and indexname = 'study_tasks_user_due_idx';
select indexname
from pg_indexes
where schemaname = 'public'
  and indexname = 'focus_sessions_user_completed_idx';
select relrowsecurity
from pg_class
where oid = 'public.flashcards'::regclass;
select relrowsecurity
from pg_class
where oid = 'public.study_tasks'::regclass;
select relrowsecurity
from pg_class
where oid = 'public.focus_sessions'::regclass;
