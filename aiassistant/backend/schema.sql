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

-- 4. Study planner used by the dashboard and planner screen
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

-- 5. Flashcards table for revision & spaced repetition
create table if not exists flashcards (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    document_id uuid references documents(id) on delete set null,
    front text not null,
    back text not null,
    category text default 'General',
    status text default 'due',
    review_count int default 0,
    last_reviewed timestamp with time zone,
    created_at timestamp with time zone default now()
);

create index if not exists flashcards_user_idx
    on flashcards(user_id, status);

-- 6. Quizzes and assessments table
create table if not exists quizzes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    document_id uuid references documents(id) on delete set null,
    title text not null,
    score int default 0,
    total_questions int default 0,
    questions jsonb default '[]'::jsonb,
    created_at timestamp with time zone default now()
);

-- 7. Optimized counter functions
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

-- 8. Enable Row Level Security (RLS) with permissive policies for API client access
alter table users enable row level security;
alter table documents enable row level security;
alter table questions enable row level security;
alter table study_plans enable row level security;
alter table flashcards enable row level security;
alter table quizzes enable row level security;

-- Policies allowing access for backend service and authenticated/anon client tokens:
drop policy if exists "Enable all for users" on users;
create policy "Enable all for users" on users for all using (true) with check (true);

drop policy if exists "Enable all for documents" on documents;
create policy "Enable all for documents" on documents for all using (true) with check (true);

drop policy if exists "Enable all for questions" on questions;
create policy "Enable all for questions" on questions for all using (true) with check (true);

drop policy if exists "Enable all for study_plans" on study_plans;
create policy "Enable all for study_plans" on study_plans for all using (true) with check (true);

drop policy if exists "Enable all for flashcards" on flashcards;
create policy "Enable all for flashcards" on flashcards for all using (true) with check (true);

drop policy if exists "Enable all for quizzes" on quizzes;
create policy "Enable all for quizzes" on quizzes for all using (true) with check (true);
