-- Additive migration for persistent document storage and retrieval.
-- Run this manually in the Supabase SQL editor after reviewing it.
-- The Flask backend uses SUPABASE_KEY as a server-side service-role key.

insert into storage.buckets (id, name, public)
values ('exam-documents', 'exam-documents', false)
on conflict (id) do update
set name = excluded.name,
    public = false;

alter table public.documents
    add column if not exists storage_bucket text default 'exam-documents',
    add column if not exists storage_path text;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'documents_id_user_id_key'
          and conrelid = 'public.documents'::regclass
    ) then
        alter table public.documents
            add constraint documents_id_user_id_key unique (id, user_id);
    end if;
end;
$$;

create table if not exists public.document_chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null,
    user_id uuid not null,
    chunk_index int not null check (chunk_index >= 0),
    content text not null,
    created_at timestamptz not null default now(),
    unique (document_id, chunk_index),
    constraint document_chunks_document_owner_fkey
        foreign key (document_id, user_id)
        references public.documents(id, user_id)
        on delete cascade
);

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'document_chunks_document_owner_fkey'
          and conrelid = 'public.document_chunks'::regclass
    ) then
        alter table public.document_chunks
            add constraint document_chunks_document_owner_fkey
            foreign key (document_id, user_id)
            references public.documents(id, user_id)
            on delete cascade;
    end if;
end;
$$;

create index if not exists document_chunks_user_document_idx
    on public.document_chunks(user_id, document_id, chunk_index);

alter table public.document_chunks enable row level security;
drop policy if exists "Document chunks are server managed" on public.document_chunks;
create policy "Document chunks are server managed"
    on public.document_chunks
    for all
    to anon, authenticated
    using (false)
    with check (false);

-- The application accesses Storage through the trusted Flask service key.
-- These policies keep the private bucket closed to direct public clients.
drop policy if exists "Exam documents are server managed" on storage.objects;
create policy "Exam documents are server managed"
    on storage.objects
    for all
    to authenticated
    using (bucket_id = 'exam-documents' and false)
    with check (bucket_id = 'exam-documents' and false);

-- Flask owns authentication and uses the server-side service-role key.
-- No browser client should access these custom-auth tables directly.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'users',
        'documents',
        'questions',
        'study_plans',
        'quiz_sessions',
        'quiz_attempts',
        'document_chunks'
    ]
    loop
        if to_regclass(format('public.%I', table_name)) is not null then
            execute format('alter table public.%I enable row level security', table_name);
            execute format('revoke all on table public.%I from anon, authenticated', table_name);
        end if;
    end loop;
end;
$$;
