-- Read-only production preflight/postflight checks.
-- This script does not create, rename, grant, revoke, or reload anything.

select table_name, column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public'
  and table_name in (
    'documents', 'document_chunk', 'document_chunks',
    'study_plans', 'study_tasks', 'flashcards', 'focus_sessions',
    'quiz_sessions', 'quiz_attempts'
  )
order by table_name, ordinal_position;

select
    to_regclass('public.document_chunk') as singular_document_chunk,
    to_regclass('public.document_chunks') as plural_document_chunks,
    to_regclass('public.flashcards') as flashcards,
    to_regclass('public.study_tasks') as study_tasks,
    to_regclass('public.focus_sessions') as focus_sessions;

select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in (
    'document_chunk', 'document_chunks',
    'flashcards', 'study_tasks', 'focus_sessions'
  )
order by tablename;

select indexname, tablename
from pg_indexes
where schemaname = 'public'
  and tablename in (
    'document_chunk', 'document_chunks',
    'flashcards', 'study_tasks', 'focus_sessions'
  )
order by tablename, indexname;

select schemaname, tablename, policyname, roles, cmd
from pg_policies
where schemaname = 'public'
  and tablename in (
    'document_chunk', 'document_chunks',
    'flashcards', 'study_tasks', 'focus_sessions'
  )
order by tablename, policyname;
