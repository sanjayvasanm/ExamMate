-- 1. Create the Users table
create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    password text not null,
    name text,
    university text,
    study_streak int default 0,
    documents_uploaded int default 0,
    total_questions int default 0,
    created_at timestamp with time zone default now(),
    last_active timestamp with time zone default now()
);

-- 2. Create the Documents table
create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete cascade,
    filename text not null,
    stored_path text not null,
    file_type text,
    summary text,
    uploaded_at timestamp with time zone default now(),
    file_size_mb numeric,
    chunks_processed int default 0,
    status text default 'uploaded',
    storage_bucket text default 'exam-documents',
    storage_path text,
    unique (id, user_id)
);

-- 3. Create the Questions/History table
create table if not exists questions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete cascade,
    document_id uuid references documents(id) on delete set null,
    question text not null,
    answer jsonb not null,
    mermaid_code text,
    mode text default 'detailed',
    marks int default 5,
    diagrams jsonb default '[]'::jsonb,
    keywords jsonb default '[]'::jsonb,
    subject text default 'General',
    asked_at timestamp with time zone default now()
);

-- 4. Create optimized counter functions
create or replace function increment_documents_uploaded(row_id uuid)
returns void as $$
update users
set documents_uploaded = documents_uploaded + 1
where id = row_id;
$$ language sql;

create or replace function increment_total_questions(row_id uuid)
returns void as $$
update users
set total_questions = total_questions + 1
where id = row_id;
$$ language sql;

-- 5. Enable Row Level Security (RLS)
-- This ensures the tables cannot be accessed directly from the frontend via the public 'anon' key.
-- Since the Flask backend acts as a secure server, it should use the 'service_role' key in Render to bypass RLS.
alter table users enable row level security;
alter table documents enable row level security;
alter table questions enable row level security;

-- 4. Study planner used by the dashboard and planner screen.
create table if not exists study_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    title text not null,
    subject text not null,
    exam_date date not null,
    notes text default '',
    completed boolean not null default false,
    created_at timestamp with time zone default now()
);

create index if not exists study_plans_user_exam_date_idx
    on study_plans(user_id, exam_date);

alter table study_plans enable row level security;

-- Compatibility additions for databases created before the API payload fields existed.
alter table documents add column if not exists file_size_mb numeric;
alter table documents add column if not exists chunks_processed int default 0;
alter table documents add column if not exists status text default 'uploaded';
alter table documents add column if not exists storage_bucket text default 'exam-documents';
alter table documents add column if not exists storage_path text;
alter table questions add column if not exists mode text default 'detailed';
alter table questions add column if not exists marks int default 5;
alter table questions add column if not exists diagrams jsonb default '[]'::jsonb;
alter table questions add column if not exists keywords jsonb default '[]'::jsonb;
alter table questions add column if not exists subject text default 'General';
-- Convert the original text answer column only when this is an older installation.
do $$
begin
    if exists (select 1 from information_schema.columns where table_name='questions' and column_name='answer' and data_type='text') then
        alter table questions alter column answer type jsonb using case when trim(answer) like '{%' then answer::jsonb else jsonb_build_object('explanation', answer) end;
    end if;
end;
$$;

create table if not exists quiz_sessions (
    id uuid primary key default gen_random_uuid(), user_id uuid not null references users(id) on delete cascade,
    document_id uuid references documents(id) on delete set null, quiz jsonb not null, created_at timestamptz default now()
);
create index if not exists quiz_sessions_user_created_idx on quiz_sessions(user_id, created_at desc);
alter table quiz_sessions enable row level security;

create table if not exists quiz_attempts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    document_id uuid references documents(id) on delete set null,
    quiz jsonb not null, answers jsonb not null, score int not null check (score >= 0),
    total int not null check (total > 0), created_at timestamp with time zone default now()
);
create index if not exists quiz_attempts_user_created_idx on quiz_attempts(user_id, created_at desc);
alter table quiz_attempts enable row level security;

create table if not exists document_chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null,
    user_id uuid not null,
    chunk_index int not null check (chunk_index >= 0),
    content text not null,
    created_at timestamp with time zone default now(),
    unique(document_id, chunk_index),
    foreign key (document_id, user_id)
        references documents(id, user_id)
        on delete cascade
);
create index if not exists document_chunks_user_document_idx
    on document_chunks(user_id, document_id, chunk_index);
alter table document_chunks enable row level security;
drop policy if exists "Document chunks are server managed" on document_chunks;
create policy "Document chunks are server managed"
    on document_chunks
    for all
    to anon, authenticated
    using (false)
    with check (false);

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
        execute format('alter table %I enable row level security', table_name);
        execute format('revoke all on table %I from anon, authenticated', table_name);
    end loop;
end;
$$;
