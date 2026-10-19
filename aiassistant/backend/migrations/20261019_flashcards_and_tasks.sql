-- Additive migration for persistent flashcards and richer study tasks.
-- Review and run manually in Supabase SQL Editor. This is not auto-applied.

create table if not exists public.flashcards (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    document_id uuid references public.documents(id) on delete set null,
    topic text not null default 'General revision',
    front text not null,
    back text not null,
    interval_days integer not null default 0 check (interval_days >= 0),
    ease_factor numeric(4,2) not null default 2.5 check (ease_factor >= 1.3),
    last_rating text check (last_rating in ('again', 'hard', 'good', 'easy')),
    next_review_at timestamptz not null default now(),
    reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists flashcards_user_review_idx
    on public.flashcards(user_id, next_review_at);

alter table public.flashcards enable row level security;
revoke all on table public.flashcards from anon, authenticated;
drop policy if exists "Flashcards are server managed" on public.flashcards;
create policy "Flashcards are server managed"
    on public.flashcards for all to anon, authenticated
    using (false) with check (false);

alter table public.study_plans add column if not exists priority text not null default 'medium';
alter table public.study_plans add column if not exists estimated_minutes integer not null default 30;
alter table public.study_plans add column if not exists topic text not null default '';
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'study_plans_priority_check'
          and conrelid = 'public.study_plans'::regclass
    ) then
        alter table public.study_plans add constraint study_plans_priority_check
            check (priority in ('low', 'medium', 'high'));
    end if;
end;
$$;

create table if not exists public.study_tasks (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    plan_id uuid references public.study_plans(id) on delete set null,
    title text not null,
    subject text not null default '',
    topic text not null default '',
    due_date date not null,
    priority text not null default 'medium' check (priority in ('low', 'medium', 'high')),
    estimated_minutes integer not null default 30 check (estimated_minutes between 5 and 480),
    completed boolean not null default false,
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create index if not exists study_tasks_user_due_idx
    on public.study_tasks(user_id, completed, due_date);

alter table public.study_tasks enable row level security;
revoke all on table public.study_tasks from anon, authenticated;
drop policy if exists "Study tasks are server managed" on public.study_tasks;
create policy "Study tasks are server managed"
    on public.study_tasks for all to anon, authenticated
    using (false) with check (false);

create table if not exists public.focus_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    task_id uuid references public.study_tasks(id) on delete set null,
    subject text not null default '',
    work_minutes integer not null check (work_minutes between 1 and 120),
    completed_at timestamptz not null default now()
);

create index if not exists focus_sessions_user_completed_idx
    on public.focus_sessions(user_id, completed_at desc);

alter table public.focus_sessions enable row level security;
revoke all on table public.focus_sessions from anon, authenticated;
drop policy if exists "Focus sessions are server managed" on public.focus_sessions;
create policy "Focus sessions are server managed"
    on public.focus_sessions for all to anon, authenticated
    using (false) with check (false);
