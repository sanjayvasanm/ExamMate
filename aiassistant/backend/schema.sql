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
    uploaded_at timestamp with time zone default now()
);

-- 3. Create the Questions/History table
create table if not exists questions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete cascade,
    document_id uuid references documents(id) on delete set null,
    question text not null,
    answer text not null,
    mermaid_code text,
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
