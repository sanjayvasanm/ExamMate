-- Read-only preflight and post-migration verification.
-- Run this in the Supabase SQL editor before and after applying
-- 20261019_persistent_documents.sql. It does not modify data.

-- Existing table columns and types.
SELECT table_name, column_name, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'users', 'documents', 'document_chunk', 'study_plans',
      'quiz_sessions', 'quiz_attempts'
  )
ORDER BY table_name, ordinal_position;

-- Detect the singular live table and any legacy plural table without changing
-- either one. Both existing at once requires manual resolution.
SELECT
    to_regclass('public.document_chunk') AS singular_table,
    to_regclass('public.document_chunks') AS legacy_plural_table;

-- Existing primary keys and foreign keys.
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
LEFT JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage AS ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN (
      'users', 'documents', 'document_chunk', 'study_plans',
      'quiz_sessions', 'quiz_attempts'
  )
  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;

-- RLS state and table privileges.
SELECT
    schemaname,
    tablename,
    rowsecurity,
    has_table_privilege('anon', format('%I.%I', schemaname, tablename), 'SELECT') AS anon_can_select,
    has_table_privilege('authenticated', format('%I.%I', schemaname, tablename), 'SELECT') AS authenticated_can_select
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
      'users', 'documents', 'document_chunk', 'study_plans',
      'quiz_sessions', 'quiz_attempts'
  )
ORDER BY tablename;

-- Policies on the application and Storage tables.
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE (schemaname = 'public' AND tablename IN (
    'users', 'documents', 'document_chunk', 'study_plans',
    'quiz_sessions', 'quiz_attempts'
))
   OR (schemaname = 'storage' AND tablename = 'objects')
ORDER BY schemaname, tablename, policyname;

-- Storage buckets and privacy.
SELECT id, name, public, file_size_limit, allowed_mime_types
FROM storage.buckets
WHERE id = 'exam-documents' OR name = 'exam-documents';

-- Existing documents that cannot satisfy ownership constraints.
SELECT COUNT(*) AS documents_with_null_user_id
FROM public.documents
WHERE user_id IS NULL;

-- Read-only ownership/orphan checks. These are conditional so the script can
-- be run before the migration, when one or more tables may not exist.
do $$
declare
    mismatch_count bigint;
    orphan_count bigint;
begin
    if to_regclass('public.document_chunk') is null then
        raise notice 'document_chunk is missing';
    else
        execute $query$
            select count(*)
            from public.document_chunk as dc
            join public.documents as d on d.id = dc.document_id
            where dc.user_id is distinct from d.user_id
        $query$ into mismatch_count;
        raise notice 'document_chunk owner mismatches: %', mismatch_count;
    end if;

    if to_regclass('public.study_plans') is null then
        raise notice 'study_plans is missing';
    else
        execute $query$
            select count(*)
            from public.study_plans as sp
            left join public.users as u on u.id = sp.user_id
            where u.id is null
        $query$ into orphan_count;
        raise notice 'study_plans orphan user references: %', orphan_count;
    end if;

    if to_regclass('public.quiz_sessions') is null then
        raise notice 'quiz_sessions is missing';
    else
        execute $query$
            select count(*)
            from public.quiz_sessions as qs
            left join public.users as u on u.id = qs.user_id
            where u.id is null
        $query$ into orphan_count;
        raise notice 'quiz_sessions orphan user references: %', orphan_count;
    end if;

    if to_regclass('public.quiz_attempts') is null then
        raise notice 'quiz_attempts is missing';
    else
        execute $query$
            select count(*)
            from public.quiz_attempts as qa
            left join public.users as u on u.id = qa.user_id
            left join public.documents as d on d.id = qa.document_id
            where u.id is null
               or (qa.document_id is not null and d.id is null)
        $query$ into orphan_count;
        raise notice 'quiz_attempts orphan user/document references: %', orphan_count;
    end if;
end;
$$;

-- Required table/column presence for the Flask API. A missing table returns
-- zero rows rather than changing anything.
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
      (table_name = 'study_plans' AND column_name IN (
          'id', 'user_id', 'title', 'subject', 'exam_date', 'notes',
          'completed', 'created_at'
      ))
      OR (table_name = 'quiz_sessions' AND column_name IN (
          'id', 'user_id', 'document_id', 'quiz', 'created_at'
      ))
      OR (table_name = 'quiz_attempts' AND column_name IN (
          'id', 'user_id', 'document_id', 'quiz', 'answers', 'score',
          'total', 'created_at'
      ))
  )
ORDER BY table_name, ordinal_position;
