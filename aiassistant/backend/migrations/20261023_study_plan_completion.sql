-- Additive migration for planner completion timestamps.
-- Run manually in the Supabase SQL editor after reviewing it.

alter table public.study_plans
    add column if not exists completed_at timestamptz;
