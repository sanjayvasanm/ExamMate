-- Safe, idempotent document-chunk relation reconciliation.
-- Review and run manually only after the verification query confirms the
-- expected columns. This does not drop or truncate data.

do $$
begin
    if to_regclass('public.document_chunks') is not null
       and to_regclass('public.document_chunk') is not null then
        raise exception
            'Both public.document_chunk and public.document_chunks exist; resolve manually before continuing';
    elsif to_regclass('public.document_chunk') is not null then
        alter table public.document_chunk rename to document_chunks;
    end if;
end;
$$;

do $$
begin
    if to_regclass('public.documents') is null then
        raise exception 'public.documents must exist before creating document_chunks';
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'documents_id_user_id_key'
          and conrelid = 'public.documents'::regclass
    ) then
        alter table public.documents
            add constraint documents_id_user_id_key unique (id, user_id);
    end if;

    if to_regclass('public.document_chunks') is null then
        create table public.document_chunks (
            id uuid primary key default gen_random_uuid(),
            document_id uuid not null,
            user_id uuid not null,
            chunk_index integer not null check (chunk_index >= 0),
            content text not null,
            created_at timestamptz not null default now(),
            unique (document_id, chunk_index),
            constraint document_chunks_document_owner_fkey
                foreign key (document_id, user_id)
                references public.documents(id, user_id)
                on delete cascade
        );
    end if;
end;
$$;

create index if not exists document_chunks_user_document_idx
    on public.document_chunks(user_id, document_id, chunk_index);

alter table public.document_chunks enable row level security;
revoke all on table public.document_chunks from anon, authenticated;
drop policy if exists "Document chunks are server managed" on public.document_chunks;
create policy "Document chunks are server managed"
    on public.document_chunks for all to anon, authenticated
    using (false) with check (false);

notify pgrst, 'reload schema';
