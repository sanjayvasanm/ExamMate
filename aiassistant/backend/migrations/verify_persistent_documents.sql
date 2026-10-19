-- Read-only preflight and post-migration verification.
-- Run this in the Supabase SQL editor before and after applying
-- 20261019_persistent_documents.sql. It does not modify data.

-- Existing table columns and types.
SELECT table_name, column_name, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('users', 'documents', 'document_chunks')
ORDER BY table_name, ordinal_position;

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
  AND tc.table_name IN ('users', 'documents', 'document_chunks')
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
  AND tablename IN ('users', 'documents', 'document_chunks')
ORDER BY tablename;

-- Policies on the application and Storage tables.
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE (schemaname = 'public' AND tablename IN ('users', 'documents', 'document_chunks'))
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

-- After document_chunks exists: detect owner mismatches before relying on the
-- composite foreign key. This query is intentionally read-only.
SELECT dc.document_id, dc.user_id AS chunk_user_id, d.user_id AS document_user_id
FROM public.document_chunks AS dc
JOIN public.documents AS d ON d.id = dc.document_id
WHERE dc.user_id IS DISTINCT FROM d.user_id
LIMIT 100;
